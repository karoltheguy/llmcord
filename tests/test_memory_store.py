import os
import sqlite3
from pathlib import Path

import pytest

from memory_store import Claim, MemoryStore, MemoryStoreError


async def test_upsert_then_get_round_trips_across_instances(tmp_path):
    db_path = tmp_path / "memory.db"
    store1 = MemoryStore(db_path)
    await store1.initialize()
    await store1.upsert(123, "user memory data")

    store2 = MemoryStore(db_path)
    await store2.initialize()
    assert await store2.get(123) == "user memory data"


async def test_get_returns_none_for_unknown_user(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    assert await store.get(999) is None


async def test_upsert_replaces_existing_memory(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.upsert(123, "initial memory")
    await store.upsert(123, "updated memory")
    assert await store.get(123) == "updated memory"


async def test_delete_removes_user_memory(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.upsert(123, "to be deleted")
    await store.delete(123)
    assert await store.get(123) is None


async def test_multi_subject_claim_round_trips_once_and_returns_for_each_subject(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222, 333},
        claims=[
            Claim(
                id=None,
                source_id=111,
                subjects={222, 333},
                text="they had a fight at the party",
            )
        ],
    )

    claims = await store.claims_by(111)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.subjects == {222, 333}
    assert claim.text == "they had a fight at the party"
    assert claim.source_id == 111
    assert isinstance(claim.id, int)
    assert claim.created_at is not None

    about_222 = await store.claims_about({222})
    about_333 = await store.claims_about({333})
    assert len(about_222) == 1
    assert len(about_333) == 1
    assert about_222[0].id == about_333[0].id

    assert await store.claims_about({444}) == []


async def test_initialize_adds_claim_tables_to_an_existing_database(tmp_path):
    db_path = tmp_path / "memory.db"
    store1 = MemoryStore(db_path)
    await store1.initialize()
    await store1.upsert(1, "existing memory")

    store2 = MemoryStore(db_path)
    await store2.initialize()
    await store2.replace_claims(
        source_id=555,
        scope_subject_ids={666},
        claims=[
            Claim(
                id=None,
                source_id=555,
                subjects={666},
                text="claim written after upgrade",
            )
        ],
    )
    claims = await store2.claims_by(555)
    assert len(claims) == 1
    assert claims[0].text == "claim written after upgrade"
    assert await store2.get(1) == "existing memory"


async def test_echoed_claim_id_is_updated_in_place_and_keeps_its_created_at(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222},
        claims=[
            Claim(
                id=None,
                source_id=111,
                subjects={222},
                text="original text",
            )
        ],
    )

    seeded = await store.claims_by(111)
    assert len(seeded) == 1
    original_id = seeded[0].id
    original_created_at = seeded[0].created_at

    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222},
        claims=[
            Claim(
                id=original_id,
                source_id=111,
                subjects={222},
                text="updated text",
            )
        ],
    )

    claims = await store.claims_by(111)
    assert len(claims) == 1
    assert claims[0].id == original_id
    assert claims[0].created_at == original_created_at
    assert claims[0].text == "updated text"


async def test_unechoed_in_scope_claim_is_dropped_while_echoed_one_survives(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222},
        claims=[
            Claim(
                id=None,
                source_id=111,
                subjects={222},
                text="kept claim",
            ),
            Claim(
                id=None,
                source_id=111,
                subjects={222},
                text="dropped claim",
            ),
        ],
    )

    seeded = await store.claims_by(111)
    kept_id = next(claim.id for claim in seeded if claim.text == "kept claim")

    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222},
        claims=[
            Claim(
                id=kept_id,
                source_id=111,
                subjects={222},
                text="kept claim",
            )
        ],
    )

    claims = await store.claims_by(111)
    assert len(claims) == 1
    assert claims[0].text == "kept claim"
    assert claims[0].id == kept_id


async def test_claims_outside_the_scope_are_untouched(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222},
        claims=[
            Claim(
                id=None,
                source_id=111,
                subjects={222},
                text="claim about 222",
            )
        ],
    )
    await store.replace_claims(
        source_id=111,
        scope_subject_ids={999},
        claims=[
            Claim(
                id=None,
                source_id=111,
                subjects={999},
                text="claim about 999",
            )
        ],
    )

    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222},
        claims=[],
    )

    assert await store.claims_about({222}) == []
    remaining = await store.claims_about({999})
    assert len(remaining) == 1


async def test_delete_claims_for_removes_claims_the_user_authored_and_claims_about_them(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222},
        claims=[
            Claim(
                id=None,
                source_id=111,
                subjects={222},
                text="alice about bob",
            )
        ],
    )
    await store.replace_claims(
        source_id=333,
        scope_subject_ids={111},
        claims=[
            Claim(
                id=None,
                source_id=333,
                subjects={111},
                text="carol about alice",
            )
        ],
    )
    await store.replace_claims(
        source_id=333,
        scope_subject_ids={444},
        claims=[
            Claim(
                id=None,
                source_id=333,
                subjects={444},
                text="carol about dave",
            )
        ],
    )

    await store.delete_claims_for(111)

    assert await store.claims_by(111) == []
    assert await store.claims_about({111}) == []
    remaining = await store.claims_by(333)
    assert len(remaining) == 1
    assert remaining[0].text == "carol about dave"


async def test_delete_claims_for_leaves_no_orphaned_claim_subject_rows(tmp_path):
    db_path = tmp_path / "memory.db"
    store = MemoryStore(db_path)
    await store.initialize()
    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222, 333},
        claims=[
            Claim(
                id=None,
                source_id=111,
                subjects={222, 333},
                text="they had a fight at the party",
            )
        ],
    )

    await store.delete_claims_for(111)

    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM claim_subjects").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0


async def test_claims_by_narrows_to_the_requested_subjects(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222},
        claims=[
            Claim(
                id=None,
                source_id=111,
                subjects={222},
                text="claim about 222",
            )
        ],
    )
    await store.replace_claims(
        source_id=111,
        scope_subject_ids={999},
        claims=[
            Claim(
                id=None,
                source_id=111,
                subjects={999},
                text="claim about 999",
            )
        ],
    )

    all_claims = await store.claims_by(111)
    assert len(all_claims) == 2

    narrowed = await store.claims_by(111, subject_ids={999})
    assert len(narrowed) == 1
    assert narrowed[0].text == "claim about 999"


async def test_claims_about_can_exclude_a_source(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.replace_claims(
        source_id=111,
        scope_subject_ids={222},
        claims=[
            Claim(
                id=None,
                source_id=111,
                subjects={222},
                text="alice about bob",
            )
        ],
    )
    await store.replace_claims(
        source_id=333,
        scope_subject_ids={222},
        claims=[
            Claim(
                id=None,
                source_id=333,
                subjects={222},
                text="carol about bob",
            )
        ],
    )

    all_about_222 = await store.claims_about({222})
    assert len(all_about_222) == 2

    excluded = await store.claims_about({222}, exclude_source=111)
    assert len(excluded) == 1
    assert excluded[0].source_id == 333


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permission bits")
async def test_initialize_reports_context_when_db_cannot_be_opened(tmp_path):
    unwritable_dir = tmp_path / "unwritable"
    unwritable_dir.mkdir()
    db_path = unwritable_dir / "memory.db"
    unwritable_dir.chmod(0o500)
    try:
        store = MemoryStore(db_path)
        with pytest.raises(MemoryStoreError) as exc_info:
            await store.initialize()

        message = str(exc_info.value)
        assert str(Path(db_path).resolve()) in message
        assert str(os.geteuid()) in message
        assert "writable" in message.lower()
    finally:
        unwritable_dir.chmod(0o700)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permission bits")
async def test_initialize_reports_context_when_parent_cannot_be_created(tmp_path):
    unwritable_dir = tmp_path / "unwritable"
    unwritable_dir.mkdir()
    unwritable_dir.chmod(0o500)
    db_path = unwritable_dir / "sub" / "memory.db"
    try:
        store = MemoryStore(db_path)
        with pytest.raises(MemoryStoreError) as exc_info:
            await store.initialize()

        message = str(exc_info.value)
        assert str(Path(db_path).resolve()) in message
        assert str(os.geteuid()) in message
        assert "writable" in message.lower()
    finally:
        unwritable_dir.chmod(0o700)
