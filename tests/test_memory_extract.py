from types import SimpleNamespace

from memory_extract import extract_memory


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
    assert result == "likes cats; lives in Montreal"


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
    assert result == "x" * 10


async def test_returns_none_when_model_returns_blank():
    client = StubClient(response="   ")
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory=None,
        exchange="msg",
        prompt="prompt",
    )
    assert result is None


async def test_returns_none_when_client_raises():
    client = StubClient(should_raise=True)
    result = await extract_memory(
        client=client,
        model="gpt-4o",
        existing_memory="likes cats",
        exchange="msg",
        prompt="prompt",
    )
    assert result is None
