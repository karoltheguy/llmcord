from memory_store import MemoryStore


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
