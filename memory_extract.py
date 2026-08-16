import logging
from typing import Any

DEFAULT_EXTRACTION_PROMPT = """Review the existing memory and recent exchange with the user.
Return the COMPLETE updated memory for the user as plain text.
Merge and consolidate new facts with existing memory rather than appending.
Keep only durable facts, preferences, and details about the user.
Omit the conversation itself and transient context.
Return nothing at all if there is nothing worth remembering."""


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
        user_content = f"Existing memory:\n{existing_memory or '(none)'}\n\nRecent exchange:\n{exchange}"
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
        )
        content = response.choices[0].message.content if response.choices and response.choices[0].message else None
        return content.strip()[:max_chars] if content and content.strip() else None
    except Exception:
        logging.exception("Error while extracting memory")
        return None
