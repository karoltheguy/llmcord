import llmcord
from memory_commands import bump_epoch
from memory_extract import ExtractedClaim, ExtractionResult
import memory_store as memory_store_module


class FakeStore:
    def __init__(self, claims_by_result=None):
        self.upsert_calls = []
        self.claims_by_calls = []
        self.replace_claims_calls = []
        self._claims_by_result = claims_by_result or []

    async def get(self, user_id):
        return None

    async def upsert(self, user_id, text):
        self.upsert_calls.append((user_id, text))

    async def claims_by(self, source_id, subject_ids=None, limit=50):
        self.claims_by_calls.append((source_id, subject_ids))
        return self._claims_by_result

    async def replace_claims(self, source_id, scope_subject_ids, claims):
        self.replace_claims_calls.append((source_id, scope_subject_ids, claims))


def make_config(**overrides):
    config = {
        "memory_model": "p/m",
        "providers": {"p": {"base_url": "http://x", "api_key": "k"}},
    }
    config.update(overrides)
    return config


def make_extract_stub(result=None, recorder=None, side_effect=None):
    result = result if result is not None else ExtractionResult(self_memory="self fact", claims=[])

    async def stub(**kwargs):
        if recorder is not None:
            recorder.append(kwargs)
        if side_effect is not None:
            side_effect()
        return result

    return stub


async def test_claims_written_with_threaded_participant_set_as_scope(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(llmcord, "memory_store", store)
    monkeypatch.setattr(llmcord, "forget_epochs", {})

    result = ExtractionResult(
        self_memory=None,
        claims=[ExtractedClaim(id=None, subjects={222}, text="claims about 222")],
    )
    monkeypatch.setattr(llmcord, "extract_memory", make_extract_stub(result=result))

    await llmcord.update_user_memory(
        make_config(), 111, "exchange text", participants={111, 222, 333}, bot_id=999
    )

    assert len(store.replace_claims_calls) == 1
    source_id, scope_subject_ids, claims = store.replace_claims_calls[0]
    assert source_id == 111
    assert scope_subject_ids == {222, 333}
    assert all(isinstance(c, memory_store_module.Claim) for c in claims)
    assert all(c.source_id == 111 for c in claims)


async def test_speaker_bot_and_max_claims_reach_extract_memory(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(llmcord, "memory_store", store)
    monkeypatch.setattr(llmcord, "forget_epochs", {})

    recorder = []
    monkeypatch.setattr(llmcord, "extract_memory", make_extract_stub(recorder=recorder))

    await llmcord.update_user_memory(
        make_config(), 111, "exchange text", participants={111, 222, 333}, bot_id=999
    )

    assert recorder[0]["speaker_id"] == 111
    assert recorder[0]["bot_id"] == 999
    assert recorder[0]["max_claims"] == 20

    recorder.clear()
    monkeypatch.setattr(llmcord, "extract_memory", make_extract_stub(recorder=recorder))
    await llmcord.update_user_memory(
        make_config(memory_max_claims_per_extraction=5),
        111,
        "exchange text",
        participants={111, 222, 333},
        bot_id=999,
    )

    assert recorder[0]["max_claims"] == 5


async def test_known_claim_ids_come_from_claims_by(monkeypatch):
    seeded = [
        memory_store_module.Claim(id=12, source_id=111, subjects={222}, text="a"),
        memory_store_module.Claim(id=13, source_id=111, subjects={333}, text="b"),
    ]
    store = FakeStore(claims_by_result=seeded)
    monkeypatch.setattr(llmcord, "memory_store", store)
    monkeypatch.setattr(llmcord, "forget_epochs", {})

    recorder = []
    monkeypatch.setattr(llmcord, "extract_memory", make_extract_stub(recorder=recorder))

    await llmcord.update_user_memory(
        make_config(), 111, "exchange text", participants={111, 222, 333}, bot_id=999
    )

    assert len(store.claims_by_calls) == 1
    source_id, subject_ids = store.claims_by_calls[0]
    assert source_id == 111
    assert subject_ids == {222, 333}
    assert recorder[0]["known_claim_ids"] == {12, 13}


async def test_speaker_forget_mid_extraction_discards_everything(monkeypatch):
    store = FakeStore()
    epochs = {}
    monkeypatch.setattr(llmcord, "memory_store", store)
    monkeypatch.setattr(llmcord, "forget_epochs", epochs)

    result = ExtractionResult(
        self_memory="self fact",
        claims=[ExtractedClaim(id=None, subjects={222}, text="claim")],
    )

    def bump_speaker():
        bump_epoch(epochs, 111)

    monkeypatch.setattr(llmcord, "extract_memory", make_extract_stub(result=result, side_effect=bump_speaker))

    await llmcord.update_user_memory(
        make_config(), 111, "exchange text", participants={111, 222, 333}, bot_id=999
    )

    assert store.upsert_calls == []
    assert store.replace_claims_calls == []


async def test_subject_forget_mid_extraction_drops_only_that_claim(monkeypatch):
    store = FakeStore()
    epochs = {}
    monkeypatch.setattr(llmcord, "memory_store", store)
    monkeypatch.setattr(llmcord, "forget_epochs", epochs)

    result = ExtractionResult(
        self_memory="self fact",
        claims=[
            ExtractedClaim(id=None, subjects={222}, text="about 222"),
            ExtractedClaim(id=None, subjects={333}, text="about 333"),
        ],
    )

    def bump_subject():
        bump_epoch(epochs, 222)

    monkeypatch.setattr(llmcord, "extract_memory", make_extract_stub(result=result, side_effect=bump_subject))

    await llmcord.update_user_memory(
        make_config(), 111, "exchange text", participants={111, 222, 333}, bot_id=999
    )

    assert len(store.replace_claims_calls) == 1
    _, _, claims = store.replace_claims_calls[0]
    assert len(claims) == 1
    assert claims[0].subjects == {333}
    assert store.upsert_calls == [(111, "self fact")]


async def test_no_participants_preserves_dm_behavior(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(llmcord, "memory_store", store)
    monkeypatch.setattr(llmcord, "forget_epochs", {})

    result = ExtractionResult(self_memory="self fact", claims=[])
    monkeypatch.setattr(llmcord, "extract_memory", make_extract_stub(result=result))

    await llmcord.update_user_memory(make_config(), 111, "exchange text")

    assert store.claims_by_calls == []
    assert store.replace_claims_calls == []
    assert store.upsert_calls == [(111, "self fact")]


async def test_claim_about_absent_person_is_kept(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(llmcord, "memory_store", store)
    monkeypatch.setattr(llmcord, "forget_epochs", {})

    result = ExtractionResult(
        self_memory=None,
        claims=[ExtractedClaim(id=None, subjects={777}, text="Bob is allergic to peanuts")],
    )
    monkeypatch.setattr(llmcord, "extract_memory", make_extract_stub(result=result))

    await llmcord.update_user_memory(
        make_config(), 111, "exchange text", participants={111, 222}, bot_id=999
    )

    assert len(store.replace_claims_calls) == 1
    source_id, scope_subject_ids, claims = store.replace_claims_calls[0]
    assert scope_subject_ids == {222}
    assert any(c.subjects == {777} for c in claims)
