from memory_store import Claim
from prompt import render_claim_line

NO_MEMORY_MESSAGE = "I don't have anything stored about you yet."
FORGET_DONE_MESSAGE = (
    "Done. I've deleted everything I had stored about you, including what you told me about "
    "other people and what other people told me about you."
)
MEMORY_HEADER = "Here's what I have stored about you:"
CLAIMS_HEADER = "What you've told me about others:"


def format_memory_reply(memory: str | None, limit: int = 2000, claims: list[Claim] | None = None) -> str:
    sections = []

    if memory and memory.strip():
        sections.append(f"{MEMORY_HEADER}\n{memory.strip()}")

    if claims:
        claims_section = "\n".join(render_claim_line(claim.subjects, {}, claim.text) for claim in claims)
        sections.append(f"{CLAIMS_HEADER}\n{claims_section}")

    if not sections:
        return NO_MEMORY_MESSAGE

    text = "\n\n".join(sections)
    if len(text) <= limit:
        return text

    marker = "\n[truncated]"
    available = limit - len(marker)
    if available >= 0:
        return f"{text[:available]}{marker}"

    return text[:limit]


async def read_memory(store, user_id: int, limit: int = 2000) -> str:
    memory = await store.get(user_id)
    claims = await store.claims_by(user_id)
    return format_memory_reply(memory, limit, claims)


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
    await store.delete_claims_for(user_id)
    return FORGET_DONE_MESSAGE
