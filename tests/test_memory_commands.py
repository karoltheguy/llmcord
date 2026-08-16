from memory_commands import (
    FORGET_DONE_MESSAGE,
    NO_MEMORY_MESSAGE,
    bump_epoch,
    current_epoch,
    format_memory_reply,
    forget_memory,
    may_write_memory,
    read_memory,
)
from memory_store import MemoryStore


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

