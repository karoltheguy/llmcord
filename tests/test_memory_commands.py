from memory_commands import (
    FORGET_DONE_MESSAGE,
    NO_MEMORY_MESSAGE,
    format_memory_reply,
    forget_memory,
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
