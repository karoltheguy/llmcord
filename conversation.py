def build_user_prefix(*, user_id: int, display_name: str | None, max_name: int = 64) -> str:
    """Build the user mention and display name prefix for a message."""
    name = (display_name or "").strip()
    if not name:
        return f"<@{user_id}>: "
    return f"<@{user_id}> ({name[:max_name]}): "


def select_recent_context(*, candidates, now, window, limit, exclude_ids) -> list:
    """Select up to `limit` recent, non-excluded candidates within the window, oldest-first."""
    cutoff = now - window
    kept = []
    for entry in candidates:
        if len(kept) >= limit:
            break
        entry_id, _author_id, created_at, _is_bot = entry
        if created_at <= cutoff:
            continue
        if entry_id in exclude_ids:
            continue
        kept.append(entry)
    return list(reversed(kept))


def render_exchange(*, entries, limit: int, assistant_reply: str | None = None) -> str:
    """Render a transcript of the most recent `limit` entries, oldest-first, plus an optional reply."""
    ordered = sorted(entries, key=lambda entry: entry[0])
    kept = ordered[-limit:] if limit > 0 else []

    parts = [
        text if role == "user" else f"Assistant:\n{text}"
        for _created_at, role, text in kept
    ]

    if assistant_reply:
        parts.append(f"Assistant:\n{assistant_reply}")

    return "\n\n".join(parts)


def should_chain_to_previous(
    *,
    is_dm: bool,
    content_mentions_bot: bool,
    prev_author_id: int | None,
    curr_author_id: int,
    bot_id: int,
    prev_answered_author_id: int | None = None,
    implicit_public_chaining: bool = True,
) -> bool:
    """Decide whether a message should chain to the preceding message in the channel."""
    if prev_author_id is None:
        return False
    if is_dm:
        return False if content_mentions_bot else prev_author_id == bot_id
    if not implicit_public_chaining:
        return False if content_mentions_bot else prev_author_id == curr_author_id
    return prev_author_id == curr_author_id or (prev_author_id == bot_id and prev_answered_author_id == curr_author_id)
