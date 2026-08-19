import json
from types import SimpleNamespace

import pytest

from memory_extract import ExtractedClaim, ExtractionResult, extract_memory


class StubClient:
    def __init__(self, response: str | None = None, should_raise: bool = False):
        self.response = response
        self.should_raise = should_raise
        self.call_count = 0
        self.last_kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.call_count += 1
        self.last_kwargs = kwargs
        if self.should_raise:
            raise RuntimeError("stub error")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.response))])


async def test_returns_merged_memory_from_the_model():
    client = StubClient(response="likes cats; lives in Montreal")
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory="likes cats",
        exchange="<@1>: I live in Montreal now",
        prompt="extract user memories",
    )
    assert result.self_memory == "likes cats; lives in Montreal"


async def test_prompt_carries_existing_memory_and_exchange():
    client = StubClient(response="updated memory")
    prompt = "Extract memory updates"
    existing_memory = "likes cats"
    exchange = "<@1>: I moved to Montreal"
    await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=existing_memory,
        exchange=exchange,
        prompt=prompt,
    )
    assert client.call_count == 1
    messages_str = str(client.last_kwargs.get("messages", []))
    assert prompt in messages_str
    assert existing_memory in messages_str
    assert exchange in messages_str


async def test_result_is_truncated_to_max_chars():
    client = StubClient(response="x" * 500)
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
        max_chars=10,
    )
    assert result.self_memory == "x" * 10


async def test_returns_none_when_model_returns_blank():
    client = StubClient(response="   ")
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert result.self_memory is None
    assert result.claims == []


@pytest.mark.parametrize(
    "response",
    ["(none)", "none", "None.", "N/A", "nothing", "null", "  **none**  ", "[empty]", "_", "*", "()", "-", " . "],
)
async def test_returns_none_for_placeholder_responses(response):
    client = StubClient(response=response)
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert result.self_memory is None
    assert result.claims == []


async def test_keeps_real_memory_that_merely_mentions_a_placeholder_word():
    client = StubClient(response="Has no known allergies. Nothing else recorded.")
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert result.self_memory == "Has no known allergies. Nothing else recorded."


async def test_omits_the_existing_memory_section_when_there_is_none():
    client = StubClient(response="updated memory")
    await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert "Existing memory" not in str(client.last_kwargs.get("messages", []))


async def test_returns_none_when_client_raises():
    client = StubClient(should_raise=True)
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory="likes cats",
        exchange="msg",
        prompt="prompt",
    )
    assert result.self_memory is None
    assert result.claims == []


async def test_self_plus_claims():
    payload = {
        "self": "likes cats",
        "claims": [{"id": None, "subjects": [222, 333], "text": "loves hiking"}],
    }
    client = StubClient(response=json.dumps(payload))
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert isinstance(result, ExtractionResult)
    assert result.self_memory == "likes cats"
    assert result.claims == [ExtractedClaim(id=None, subjects={222, 333}, text="loves hiking")]


async def test_two_subject_claim_stays_one_claim():
    payload = {
        "self": None,
        "claims": [{"id": None, "subjects": [222, 333], "text": "went to Montreal together"}],
    }
    client = StubClient(response=json.dumps(payload))
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert len(result.claims) == 1
    assert result.claims[0].subjects == {222, 333}


async def test_fenced_json_parses_like_bare_json():
    payload = {
        "self": "likes cats",
        "claims": [{"id": None, "subjects": [222], "text": "loves hiking"}],
    }
    raw = json.dumps(payload)
    fenced_json = f"```json\n{raw}\n```"
    fenced_bare = f"```\n{raw}\n```"

    client_json = StubClient(response=fenced_json)
    result_json = await extract_memory(
        client=client_json,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert result_json.self_memory == "likes cats"
    assert result_json.claims == [ExtractedClaim(id=None, subjects={222}, text="loves hiking")]

    client_bare = StubClient(response=fenced_bare)
    result_bare = await extract_memory(
        client=client_bare,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert result_bare.self_memory == "likes cats"
    assert result_bare.claims == [ExtractedClaim(id=None, subjects={222}, text="loves hiking")]


async def test_malformed_json_falls_back_to_self_memory():
    client = StubClient(response="  likes cats and lives in Montreal  ")
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert result.self_memory == "likes cats and lives in Montreal"
    assert result.claims == []


async def test_placeholder_claim_text_dropped():
    payload = {
        "self": None,
        "claims": [
            {"id": None, "subjects": [222], "text": "none"},
            {"id": None, "subjects": [222], "text": "loves hiking"},
        ],
    }
    client = StubClient(response=json.dumps(payload))
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert result.claims == [ExtractedClaim(id=None, subjects={222}, text="loves hiking")]


async def test_non_integer_subjects_dropped():
    payload = {
        "self": None,
        "claims": [
            {"id": None, "subjects": ["bob", None], "text": "claim a"},
            {"id": None, "subjects": [222, "bob"], "text": "claim b"},
            {"id": None, "subjects": ["333"], "text": "claim c"},
        ],
    }
    client = StubClient(response=json.dumps(payload))
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    texts = {claim.text: claim.subjects for claim in result.claims}
    assert "claim a" not in texts
    assert texts["claim b"] == {222}
    assert texts["claim c"] == {333}


async def test_speakers_own_id_stripped():
    payload = {
        "self": None,
        "claims": [
            {"id": None, "subjects": [111, 222], "text": "claim a"},
            {"id": None, "subjects": [111], "text": "claim b"},
        ],
    }
    client = StubClient(response=json.dumps(payload))
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
        speaker_id=111,
    )
    texts = {claim.text: claim.subjects for claim in result.claims}
    assert texts["claim a"] == {222}
    assert "claim b" not in texts


async def test_bot_id_stripped():
    payload = {
        "self": None,
        "claims": [
            {"id": None, "subjects": [999, 222], "text": "claim a"},
            {"id": None, "subjects": [999], "text": "claim b"},
        ],
    }
    client = StubClient(response=json.dumps(payload))
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
        bot_id=999,
    )
    texts = {claim.text: claim.subjects for claim in result.claims}
    assert texts["claim a"] == {222}
    assert "claim b" not in texts


async def test_unsupplied_id_rejected():
    payload = {
        "self": None,
        "claims": [
            {"id": 12, "subjects": [222], "text": "known claim"},
            {"id": 77, "subjects": [222], "text": "unknown id claim"},
            {"subjects": [222], "text": "no id claim"},
        ],
    }
    client = StubClient(response=json.dumps(payload))
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
        known_claim_ids={12},
    )
    by_text = {claim.text: claim for claim in result.claims}
    assert by_text["known claim"].id == 12
    assert by_text["unknown id claim"].id is None
    assert by_text["no id claim"].id is None


async def test_claim_cap():
    payload = {
        "self": None,
        "claims": [{"id": None, "subjects": [222], "text": f"claim {i}"} for i in range(5)],
    }
    client = StubClient(response=json.dumps(payload))
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
        max_claims=2,
    )
    assert len(result.claims) == 2


async def test_self_placeholder_yields_none_and_self_truncated_to_max_chars():
    payload_placeholder = {"self": "none", "claims": []}
    client_placeholder = StubClient(response=json.dumps(payload_placeholder))
    result_placeholder = await extract_memory(
        client=client_placeholder,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert result_placeholder.self_memory is None

    payload_long = {"self": "x" * 500, "claims": []}
    client_long = StubClient(response=json.dumps(payload_long))
    result_long = await extract_memory(
        client=client_long,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
        max_chars=10,
    )
    assert result_long.self_memory == "x" * 10
