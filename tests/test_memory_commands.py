from memory_commands import (
    CLAIMS_HEADER,
    FORGET_DONE_MESSAGE,
    NO_MEMORY_MESSAGE,
    current_epoch,
    format_memory_reply,
    forget_memory,
    may_write_memory,
    read_memory,
)
from memory_store import Claim, MemoryStore


def test_no_memory_and_empty_memory_give_the_same_reply():
    assert format_memory_reply(None) == NO_MEMORY_MESSAGE
    assert format_memory_reply("") == NO_MEMORY_MESSAGE
    assert format_memory_reply("   ") == NO_MEMORY_MESSAGE


def test_stored_memory_appears_in_the_reply():
    assert "likes espresso" in format_memory_reply("likes espresso")


def test_reply_never_exceeds_the_limit():
    result = format_memory_reply("x" * 5000, limit=2000)
    assert len(result) <= 2000
    assert result != NO_MEMORY_MESSAGE
    assert len(format_memory_reply("y" * 500, limit=100)) <= 100


async def test_read_memory_returns_only_the_requested_user(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.upsert(1, "alpha facts")
    await store.upsert(2, "beta facts")

    reply = await read_memory(store, 1)
    assert "alpha facts" in reply
    assert "beta facts" not in reply


async def test_read_memory_for_unknown_user_reports_nothing_stored(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.upsert(1, "alpha facts")

    assert await read_memory(store, 999) == NO_MEMORY_MESSAGE


async def test_forget_memory_deletes_only_the_requested_user(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.upsert(1, "alpha facts")
    await store.upsert(2, "beta facts")

    result = await forget_memory(store, 1)
    assert result == FORGET_DONE_MESSAGE
    assert await store.get(1) is None
    assert await store.get(2) == "beta facts"


async def test_forget_blocks_a_write_that_started_before_it(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.upsert(1, "alpha facts")
    epochs = {}
    started = current_epoch(epochs, 1)
    await forget_memory(store, 1, epochs)
    assert may_write_memory(epochs, 1, started) is False
    assert await store.get(1) is None


def test_write_is_allowed_when_no_forget_happened():
    epochs = {}
    started = current_epoch(epochs, 1)
    assert may_write_memory(epochs, 1, started) is True
    assert current_epoch(epochs, 1) == 0


async def test_forget_only_blocks_the_forgetting_user(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.upsert(1, "alpha facts")
    await store.upsert(2, "beta facts")
    epochs = {}
    started_one = current_epoch(epochs, 1)
    started_two = current_epoch(epochs, 2)
    await forget_memory(store, 1, epochs)
    assert may_write_memory(epochs, 1, started_one) is False
    assert may_write_memory(epochs, 2, started_two) is True
    assert await store.get(2) == "beta facts"


def test_claims_appear_under_claims_header_with_bare_mentions():
    claim = Claim(id=1, source_id=1, subjects={222}, text="likes tea")
    result = format_memory_reply(None, claims=[claim])
    assert CLAIMS_HEADER in result
    assert "<@222>" in result
    assert "likes tea" in result


def test_claims_without_self_memory_do_not_report_no_memory():
    claim = Claim(id=1, source_id=1, subjects={222}, text="likes tea")
    result = format_memory_reply(None, claims=[claim])
    assert result != NO_MEMORY_MESSAGE
    assert "likes tea" in result


def test_neither_memory_nor_claims_still_reports_no_memory():
    assert format_memory_reply(None, claims=[]) == NO_MEMORY_MESSAGE
    assert format_memory_reply(None, claims=None) == NO_MEMORY_MESSAGE
    assert format_memory_reply("", claims=[]) == NO_MEMORY_MESSAGE


def test_combined_reply_still_respects_the_limit():
    claims = [Claim(id=i, source_id=1, subjects={222}, text="x" * 100) for i in range(30)]
    result = format_memory_reply("y" * 3000, limit=2000, claims=claims)
    assert len(result) <= 2000


async def test_read_memory_includes_claims_made_by_that_user_and_excludes_others(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.upsert(1, "alpha facts")
    await store.replace_claims(1, {222}, [Claim(id=None, source_id=1, subjects={222}, text="claim by one")])
    await store.replace_claims(2, {333}, [Claim(id=None, source_id=2, subjects={333}, text="claim by two")])

    reply = await read_memory(store, 1)
    assert "claim by one" in reply
    assert "claim by two" not in reply


async def test_forget_memory_clears_both_directions(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.replace_claims(1, {2}, [Claim(id=None, source_id=1, subjects={2}, text="one about two")])
    await store.replace_claims(2, {1}, [Claim(id=None, source_id=2, subjects={1}, text="two about one")])
    await store.replace_claims(3, {4}, [Claim(id=None, source_id=3, subjects={4}, text="three about four")])

    await forget_memory(store, 1)

    assert await store.claims_by(1) == []
    assert await store.claims_about({1}) == []
    remaining = await store.claims_by(3)
    assert any(c.text == "three about four" for c in remaining)


async def test_forget_memory_epoch_guard_holds_alongside_claim_deletion(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.upsert(1, "alpha facts")
    await store.replace_claims(1, {2}, [Claim(id=None, source_id=1, subjects={2}, text="one about two")])
    epochs = {}
    started = current_epoch(epochs, 1)

    await forget_memory(store, 1, epochs)

    assert may_write_memory(epochs, 1, started) is False
    assert await store.claims_by(1) == []

