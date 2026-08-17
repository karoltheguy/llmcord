"""Live tests: these call a real LLM provider and spend real tokens.

They are excluded from the default run by the `live` marker (see pyproject.toml)
and skip themselves unless the LLMCORD_E2E_* variables are set:

    LLMCORD_E2E_BASE_URL=https://openrouter.ai/api/v1
    LLMCORD_E2E_API_KEY=sk-...
    LLMCORD_E2E_MODEL=openai/gpt-4o-mini

    pytest -m live

Model output is not deterministic, so nothing here asserts on exact strings. The
assertions are on properties the extraction prompt promises: durable facts
survive, transient chatter does not, and existing memory is merged rather than
replaced.
"""

import asyncio
import os

import pytest

from memory_commands import bump_epoch
from memory_extract import DEFAULT_EXTRACTION_PROMPT, extract_memory
from memory_store import MemoryStore

# A default `pytest` run must collect this file without the bot's runtime
# dependencies, so `openai` and `llmcord` are imported where they are used.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:
    pass

pytestmark = pytest.mark.live

BASE_URL = os.environ.get("LLMCORD_E2E_BASE_URL")
API_KEY = os.environ.get("LLMCORD_E2E_API_KEY")
MODEL = os.environ.get("LLMCORD_E2E_MODEL")

requires_provider = pytest.mark.skipif(
    not (BASE_URL and API_KEY and MODEL),
    reason="set LLMCORD_E2E_BASE_URL, LLMCORD_E2E_API_KEY and LLMCORD_E2E_MODEL to run live tests",
)


@pytest.fixture
def live_client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)


@pytest.fixture(scope="session")
def provider_reachable():
    """One minimal completion, so a broken endpoint fails loudly.

    `extract_memory` turns every exception into None, which is also what
    "nothing worth remembering" looks like, so tests asserting on an absent
    memory would otherwise pass during an outage.
    """
    from openai import OpenAI

    OpenAI(base_url=BASE_URL, api_key=API_KEY).chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=1,
    )


@pytest.fixture
async def store(tmp_path) -> MemoryStore:
    memory_store = MemoryStore(tmp_path / "memory.db")
    await memory_store.initialize()
    return memory_store


async def extract(client, existing_memory: str | None, exchange: str) -> str | None:
    return await extract_memory(
        client=client,
        model=MODEL,
        existing_memory=existing_memory,
        exchange=exchange,
        prompt=DEFAULT_EXTRACTION_PROMPT,
    )


@requires_provider
async def test_extraction_captures_a_planted_durable_fact(live_client):
    memory = await extract(
        live_client,
        None,
        "User:\nI ride a 2014 Kona Rove to work every day.\n\nAssistant:\nThat's a solid commuter.",
    )

    assert memory is not None
    assert "kona" in memory.lower()


@requires_provider
async def test_extraction_merges_with_existing_memory(live_client):
    memory = await extract(
        live_client,
        "Rides a 2014 Kona Rove.",
        "User:\nI'm also allergic to shellfish.\n\nAssistant:\nNoted, I'll keep that in mind.",
    )

    assert memory is not None
    lowered = memory.lower()
    assert "kona" in lowered, "existing memory was dropped instead of merged"
    assert "shellfish" in lowered, "new fact was not recorded"


@requires_provider
async def test_extraction_ignores_transient_chatter(live_client, provider_reachable):
    """Doubles as a fitness check on the candidate `memory_model`.

    Small instruct models summarise the exchange instead of declining to record
    anything, filling memory with transcripts. A failure is usually a verdict on
    the model, not a broken test. The exchange must stay free of anything
    durable, or a reasonable extraction will look like a failure.
    """
    memory = await extract(
        live_client,
        None,
        "User:\nWhat is 2 + 2?\n\nAssistant:\n4.",
    )

    assert memory is None


@requires_provider
async def test_update_user_memory_writes_through_the_real_pipeline(monkeypatch, store):
    import llmcord

    monkeypatch.setattr(llmcord, "memory_store", store)
    monkeypatch.setattr(llmcord, "forget_epochs", {})

    config = {
        "memory_model": f"live/{MODEL}",
        "providers": {"live": {"base_url": BASE_URL, "api_key": API_KEY}},
    }

    await llmcord.update_user_memory(config, 4242, "User:\nI ride a 2014 Kona Rove.\n\nAssistant:\nNice bike.")

    stored = await store.get(4242)
    assert stored is not None
    assert "kona" in stored.lower()


@requires_provider
async def test_forget_during_extraction_discards_the_write(monkeypatch, store, provider_reachable):
    """Regression cover for the /forget race, against a real (slow) API call."""
    import llmcord

    epochs: dict[int, int] = {}
    monkeypatch.setattr(llmcord, "memory_store", store)
    monkeypatch.setattr(llmcord, "forget_epochs", epochs)

    config = {
        "memory_model": f"live/{MODEL}",
        "providers": {"live": {"base_url": BASE_URL, "api_key": API_KEY}},
    }

    task = asyncio.create_task(llmcord.update_user_memory(config, 4243, "User:\nI ride a 2014 Kona Rove.\n\nAssistant:\nNice bike."))

    # /forget lands while the extraction request is still in flight.
    await asyncio.sleep(0.1)
    bump_epoch(epochs, 4243)

    await task

    assert await store.get(4243) is None
