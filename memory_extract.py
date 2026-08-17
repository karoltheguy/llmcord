import logging
from typing import Any

DEFAULT_EXTRACTION_PROMPT = """Review the existing memory and recent exchange with the user.
Return the COMPLETE updated memory for the user as plain text.
Merge and consolidate new facts with existing memory rather than appending.
Keep only durable facts, preferences, and details about the user.
Omit the conversation itself and transient context.
Return nothing at all if there is nothing worth remembering."""

# A model with nothing to record answers with a placeholder, or with stray
# punctuation, rather than an empty string. Stored, it reads as a user fact.
EMPTY_RESPONSES = frozenset(("none", "n/a", "na", "nothing", "null", "nil", "empty", "no memory", "no facts"))


def is_empty_response(content: str) -> bool:
    stripped = content.strip().strip("().[]-\"'*_ ").casefold()
    return not stripped or stripped in EMPTY_RESPONSES


async def extract_memory(
    *,
    client: Any,
    model: str,
    existing_memory: str | None,
    exchange: str,
    prompt: str,
    max_chars: int = 2000,
) -> str | None:
    """Extract and consolidate durable user facts from a conversation exchange."""
    try:
        # Absent memory omits the section: a placeholder gets echoed back as the update.
        sections = ([f"Existing memory:\n{existing_memory}"] if existing_memory and existing_memory.strip() else []) + [f"Recent exchange:\n{exchange}"]
        user_content = "\n\n".join(sections)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
        )
        content = response.choices[0].message.content if response.choices and response.choices[0].message else None
        if not content or not content.strip() or is_empty_response(content):
            return None

        return content.strip()[:max_chars]
    except Exception:
        logging.exception("Error while extracting memory")
        return None
