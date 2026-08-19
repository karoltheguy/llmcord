import llmcord
from memory_store import Claim


class FakeStore:
    def __init__(self, memories=None, claims_by_result=None, claims_about_result=None):
        self._memories = memories or {}
        self._claims_by_result = claims_by_result or []
        self._claims_about_result = claims_about_result or []
        self.get_calls = []
        self.claims_by_calls = []
        self.claims_about_calls = []

    async def get(self, user_id):
        self.get_calls.append(user_id)
        return self._memories.get(user_id)

    async def claims_by(self, source_id, subject_ids=None, limit=50):
        self.claims_by_calls.append((source_id, subject_ids))
        return self._claims_by_result

    async def claims_about(self, subject_ids, exclude_source=None, limit=50):
        self.claims_about_calls.append((subject_ids, exclude_source))
        return self._claims_about_result


def make_config(**overrides):
    config = {}
    config.update(overrides)
    return config


async def test_memory_shared_absent_or_false_keeps_others_confidential(monkeypatch):
    for config in (make_config(), make_config(memory_shared=False)):
        store = FakeStore(
            memories={111: "author self memory"},
            claims_by_result=[Claim(id=1, source_id=111, subjects={222}, text="author's own claim")],
        )
        monkeypatch.setattr(llmcord, "memory_store", store)

        blocks = await llmcord.gather_memory_blocks(config, 111, {111, 222}, {})

        joined = "\n".join(blocks)
        assert "author self memory" in joined
        assert "author's own claim" in joined
        assert store.claims_about_calls == []
        assert store.get_calls == [111]


async def test_memory_shared_true_fetches_other_participants(monkeypatch):
    store = FakeStore(
        memories={111: "author self memory", 222: "other's self memory"},
        claims_by_result=[Claim(id=1, source_id=111, subjects={222}, text="author's own claim")],
        claims_about_result=[Claim(id=2, source_id=333, subjects={222}, text="other's claim about 222")],
    )
    monkeypatch.setattr(llmcord, "memory_store", store)

    blocks = await llmcord.gather_memory_blocks(make_config(memory_shared=True), 111, {111, 222}, {})

    joined = "\n".join(blocks)
    assert "other's self memory" in joined
    assert "other's claim about 222" in joined
    assert store.claims_about_calls == [({111, 222}, 111)]
    assert 222 in store.get_calls


async def test_gather_memory_blocks_returns_empty_list_when_memory_store_is_none(monkeypatch):
    monkeypatch.setattr(llmcord, "memory_store", None)

    blocks = await llmcord.gather_memory_blocks(make_config(memory_shared=True), 111, {111, 222}, {})

    assert blocks == []
