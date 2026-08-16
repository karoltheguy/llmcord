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
