NO_MEMORY_MESSAGE = "I don't have anything stored about you yet."
FORGET_DONE_MESSAGE = "Done. I've deleted everything I had stored about you."
MEMORY_HEADER = "Here's what I have stored about you:"


def format_memory_reply(memory: str | None, limit: int = 2000) -> str:
    if not memory or not memory.strip():
        return NO_MEMORY_MESSAGE

    text = memory.strip()
    prefix = f"{MEMORY_HEADER}\n"
    if len(prefix) + len(text) <= limit:
        return f"{prefix}{text}"

    marker = "\n[truncated]"
    available = limit - len(prefix) - len(marker)
    if available >= 0:
        return f"{prefix}{text[:available]}{marker}"

    return f"{prefix}{text}"[:limit]


async def read_memory(store, user_id: int, limit: int = 2000) -> str:
    return format_memory_reply(await store.get(user_id), limit)


def current_epoch(epochs: dict[int, int], user_id: int) -> int:
    return epochs.get(user_id, 0)


def bump_epoch(epochs: dict[int, int], user_id: int) -> int:
    epochs[user_id] = epochs.get(user_id, 0) + 1
    return epochs[user_id]


def may_write_memory(epochs: dict[int, int], user_id: int, epoch_at_start: int) -> bool:
    return current_epoch(epochs, user_id) == epoch_at_start


async def forget_memory(store, user_id: int, epochs: dict[int, int] | None = None) -> str:
    if epochs is not None:
        bump_epoch(epochs, user_id)
    await store.delete(user_id)
    return FORGET_DONE_MESSAGE
