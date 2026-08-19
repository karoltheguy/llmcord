import json
import logging
from dataclasses import dataclass, field
from typing import Any

DEFAULT_EXTRACTION_PROMPT = """Review the existing memory and recent exchange with the user.
Return exactly one JSON object and nothing else, in this shape:
{"self": "...", "claims": [{"id": 12, "subjects": [222, 333], "text": "..."}]}

Put durable facts about the SPEAKER (preferences, background, details about them) in "self".

Record statements the speaker made ABOUT OTHER PEOPLE as entries in "claims". Attribute each
claim to the speaker and phrase it in the speaker's own words (e.g. "says that...",
"accused them of..."), never as an asserted fact. Preserve the speaker's tone and stance.

If a single statement concerns multiple people, list ALL of them in "subjects" for one claim
rather than splitting it into several claims. Identify people by the numeric ID found in the
`<@id> (Name):` prefixes in the exchange.

To keep an existing claim, echo its "id" unchanged. To drop an existing claim, omit it entirely.
For a new claim, omit "id".

Return {"self": null, "claims": []} when there is nothing worth remembering."""

# A model with nothing to record answers with a placeholder, or with stray
# punctuation, rather than an empty string. Stored, it reads as a user fact.
EMPTY_RESPONSES = frozenset(("none", "n/a", "na", "nothing", "null", "nil", "empty", "no memory", "no facts"))


@dataclass
class ExtractedClaim:
    id: int | None
    subjects: set[int]
    text: str


@dataclass
class ExtractionResult:
    self_memory: str | None
    claims: list[ExtractedClaim] = field(default_factory=list)


def is_empty_response(content: str) -> bool:
    stripped = content.strip().strip("().[]-\"'*_ ").casefold()
    return not stripped or stripped in EMPTY_RESPONSES


def _strip_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            lines = lines[1:-1]
            return "\n".join(lines).strip()
    return stripped


def _parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _claim_subjects(raw_subjects: Any, speaker_id: int | None, bot_id: int | None) -> set[int]:
    if not isinstance(raw_subjects, list):
        return set()
    subjects = {parsed for value in raw_subjects if (parsed := _parse_int(value)) is not None}
    subjects.discard(speaker_id)
    subjects.discard(bot_id)
    return subjects


def _clean_claim_text(value: Any, max_chars: int) -> str | None:
    if not isinstance(value, str) or not value.strip() or is_empty_response(value):
        return None
    return value.strip()[:max_chars]


def _resolve_claim_id(raw_id: Any, known_ids: set[int]) -> int | None:
    if isinstance(raw_id, bool) or not isinstance(raw_id, int):
        return None
    return raw_id if raw_id in known_ids else None


def _sanitize_claim(raw: Any, *, speaker_id: int | None, bot_id: int | None, known_ids: set[int], max_chars: int) -> ExtractedClaim | None:
    if not isinstance(raw, dict):
        return None

    subjects = _claim_subjects(raw.get("subjects"), speaker_id, bot_id)
    if not subjects:
        return None

    text = _clean_claim_text(raw.get("text"), max_chars)
    if text is None:
        return None

    return ExtractedClaim(id=_resolve_claim_id(raw.get("id"), known_ids), subjects=subjects, text=text)


def _sanitize_claims(
    raw_claims: list,
    *,
    speaker_id: int | None,
    bot_id: int | None,
    known_claim_ids: set[int] | None,
    max_chars: int,
    max_claims: int,
) -> list[ExtractedClaim]:
    known_ids = known_claim_ids or set()
    claims = [
        claim
        for raw in raw_claims
        if (claim := _sanitize_claim(raw, speaker_id=speaker_id, bot_id=bot_id, known_ids=known_ids, max_chars=max_chars)) is not None
    ]
    return claims[:max_claims]


def _parse_extraction(content: str, *, max_chars: int) -> tuple[str | None, list]:
    """Returns (self_memory, raw_claims) or raises on unparseable content."""
    de_fenced = _strip_fence(content)
    parsed = json.loads(de_fenced)
    if not isinstance(parsed, dict):
        raise ValueError("not a dict")

    self_value = parsed.get("self")
    if not isinstance(self_value, str) or not self_value.strip() or is_empty_response(self_value):
        self_memory = None
    else:
        self_memory = self_value.strip()[:max_chars]

    raw_claims = parsed.get("claims")
    if not isinstance(raw_claims, list):
        raw_claims = []

    return self_memory, raw_claims


async def extract_memory(
    *,
    client: Any,
    model: str,
    existing_memory: str | None,
    exchange: str,
    prompt: str,
    speaker_id: int | None = None,
    bot_id: int | None = None,
    known_claim_ids: set[int] | None = None,
    max_chars: int = 2000,
    max_claims: int = 20,
) -> ExtractionResult:
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
            return ExtractionResult(self_memory=None, claims=[])

        try:
            self_memory, raw_claims = _parse_extraction(content, max_chars=max_chars)
        except ValueError:
            stripped = content.strip()
            fallback = None if is_empty_response(stripped) else stripped[:max_chars]
            return ExtractionResult(self_memory=fallback, claims=[])

        claims = _sanitize_claims(
            raw_claims,
            speaker_id=speaker_id,
            bot_id=bot_id,
            known_claim_ids=known_claim_ids,
            max_chars=max_chars,
            max_claims=max_claims,
        )
        return ExtractionResult(self_memory=self_memory, claims=claims)
    except Exception:
        logging.exception("Error while extracting memory")
        return ExtractionResult(self_memory=None, claims=[])
