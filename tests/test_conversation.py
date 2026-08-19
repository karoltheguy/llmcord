from datetime import datetime, timedelta, timezone

from conversation import build_user_prefix, render_exchange, select_recent_context, should_chain_to_previous


def test_public_mention_chains_to_bot_reply_for_the_same_author():
    bot_id = 1
    curr_author_id = 2
    other_author_id = 3

    assert (
        should_chain_to_previous(
            is_dm=False,
            content_mentions_bot=True,
            prev_author_id=bot_id,
            curr_author_id=curr_author_id,
            bot_id=bot_id,
            prev_answered_author_id=curr_author_id,
            implicit_public_chaining=True,
        )
        is True
    )
    assert (
        should_chain_to_previous(
            is_dm=False,
            content_mentions_bot=True,
            prev_author_id=bot_id,
            curr_author_id=curr_author_id,
            bot_id=bot_id,
            prev_answered_author_id=other_author_id,
            implicit_public_chaining=True,
        )
        is False
    )


def test_disabled_flag_restores_mention_starts_new_conversation():
    bot_id = 1
    curr_author_id = 2

    assert (
        should_chain_to_previous(
            is_dm=False,
            content_mentions_bot=True,
            prev_author_id=bot_id,
            curr_author_id=curr_author_id,
            bot_id=bot_id,
            prev_answered_author_id=curr_author_id,
            implicit_public_chaining=False,
        )
        is False
    )
    assert (
        should_chain_to_previous(
            is_dm=False,
            content_mentions_bot=False,
            prev_author_id=curr_author_id,
            curr_author_id=curr_author_id,
            bot_id=bot_id,
            prev_answered_author_id=None,
            implicit_public_chaining=False,
        )
        is True
    )


def test_dm_behavior_is_unchanged_by_the_flag():
    bot_id = 1
    curr_author_id = 2
    other_author_id = 3

    for implicit_public_chaining in (True, False):
        assert (
            should_chain_to_previous(
                is_dm=True,
                content_mentions_bot=True,
                prev_author_id=bot_id,
                curr_author_id=curr_author_id,
                bot_id=bot_id,
                prev_answered_author_id=None,
                implicit_public_chaining=implicit_public_chaining,
            )
            is False
        )
        assert (
            should_chain_to_previous(
                is_dm=True,
                content_mentions_bot=False,
                prev_author_id=bot_id,
                curr_author_id=curr_author_id,
                bot_id=bot_id,
                prev_answered_author_id=None,
                implicit_public_chaining=implicit_public_chaining,
            )
            is True
        )
        assert (
            should_chain_to_previous(
                is_dm=True,
                content_mentions_bot=False,
                prev_author_id=other_author_id,
                curr_author_id=curr_author_id,
                bot_id=bot_id,
                prev_answered_author_id=None,
                implicit_public_chaining=implicit_public_chaining,
            )
            is False
        )


def test_public_consecutive_messages_from_the_same_author_chain():
    bot_id = 1
    curr_author_id = 2
    other_author_id = 3

    for content_mentions_bot in (True, False):
        assert (
            should_chain_to_previous(
                is_dm=False,
                content_mentions_bot=content_mentions_bot,
                prev_author_id=curr_author_id,
                curr_author_id=curr_author_id,
                bot_id=bot_id,
                prev_answered_author_id=None,
                implicit_public_chaining=True,
            )
            is True
        )

    assert (
        should_chain_to_previous(
            is_dm=False,
            content_mentions_bot=False,
            prev_author_id=other_author_id,
            curr_author_id=curr_author_id,
            bot_id=bot_id,
            prev_answered_author_id=None,
            implicit_public_chaining=True,
        )
        is False
    )


def test_no_previous_message_never_chains():
    bot_id = 1
    curr_author_id = 2

    assert (
        should_chain_to_previous(
            is_dm=True,
            content_mentions_bot=False,
            prev_author_id=None,
            curr_author_id=curr_author_id,
            bot_id=bot_id,
            prev_answered_author_id=None,
            implicit_public_chaining=True,
        )
        is False
    )
    assert (
        should_chain_to_previous(
            is_dm=False,
            content_mentions_bot=False,
            prev_author_id=None,
            curr_author_id=curr_author_id,
            bot_id=bot_id,
            prev_answered_author_id=None,
            implicit_public_chaining=True,
        )
        is False
    )


def test_build_user_prefix_includes_mention_and_name_and_ends_with_colon():
    prefix = build_user_prefix(user_id=42, display_name="Carol")
    assert "<@42>" in prefix
    assert "Carol" in prefix
    assert prefix.endswith(": ")


def test_build_user_prefix_with_none_display_name_returns_mention_only():
    assert build_user_prefix(user_id=42, display_name=None) == "<@42>: "


def test_build_user_prefix_with_whitespace_display_name_returns_mention_only():
    assert build_user_prefix(user_id=42, display_name="   ") == "<@42>: "


def test_build_user_prefix_truncates_long_display_name():
    prefix = build_user_prefix(user_id=42, display_name="N" * 500, max_name=10)
    assert "N" * 10 in prefix
    assert "N" * 11 not in prefix


def test_build_user_prefix_strips_surrounding_whitespace():
    assert (
        build_user_prefix(user_id=42, display_name="  Carol  ")
        == build_user_prefix(user_id=42, display_name="Carol")
    )


NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
WINDOW = timedelta(hours=24)


def test_drops_candidates_older_than_the_window():
    candidates = [
        (1, 100, NOW - timedelta(hours=1), False),
        (2, 100, NOW - timedelta(hours=12), False),
        (3, 100, NOW - WINDOW, False),
        (4, 100, NOW - timedelta(hours=30), False),
    ]

    result = select_recent_context(
        candidates=candidates,
        now=NOW,
        window=WINDOW,
        limit=10,
        exclude_ids=set(),
    )

    assert [entry[0] for entry in result] == [2, 1]


def test_stops_at_the_limit_keeping_the_newest():
    candidates = [
        (1, 100, NOW - timedelta(hours=1), False),
        (2, 100, NOW - timedelta(hours=2), False),
        (3, 100, NOW - timedelta(hours=3), False),
        (4, 100, NOW - timedelta(hours=4), False),
        (5, 100, NOW - timedelta(hours=5), False),
    ]

    result = select_recent_context(
        candidates=candidates,
        now=NOW,
        window=WINDOW,
        limit=2,
        exclude_ids=set(),
    )

    assert len(result) == 2
    assert [entry[0] for entry in result] == [2, 1]


def test_skips_ids_already_in_the_chain():
    candidates = [
        (1, 100, NOW - timedelta(hours=1), False),
        (2, 100, NOW - timedelta(hours=2), False),
        (3, 100, NOW - timedelta(hours=3), False),
    ]

    result = select_recent_context(
        candidates=candidates,
        now=NOW,
        window=WINDOW,
        limit=10,
        exclude_ids={2},
    )

    assert [entry[0] for entry in result] == [3, 1]


def test_returns_oldest_first():
    candidates = [
        (1, 100, NOW - timedelta(hours=1), False),
        (2, 100, NOW - timedelta(hours=2), False),
        (3, 100, NOW - timedelta(hours=3), False),
    ]

    result = select_recent_context(
        candidates=candidates,
        now=NOW,
        window=WINDOW,
        limit=10,
        exclude_ids=set(),
    )

    created_ats = [entry[2] for entry in result]
    assert created_ats == sorted(created_ats)
    assert [entry[0] for entry in result] == [3, 2, 1]


def test_limit_zero_returns_nothing():
    candidates = [
        (1, 100, NOW - timedelta(hours=1), False),
        (2, 100, NOW - timedelta(hours=2), False),
        (3, 100, NOW - timedelta(hours=3), False),
    ]

    result = select_recent_context(
        candidates=candidates,
        now=NOW,
        window=WINDOW,
        limit=0,
        exclude_ids=set(),
    )

    assert result == []


def test_render_exchange_sorts_ascending_and_joins_with_blank_line():
    entries = [
        (NOW - timedelta(minutes=1), "user", "<@111> (Alice): second"),
        (NOW - timedelta(minutes=5), "user", "<@111> (Alice): first"),
    ]

    result = render_exchange(entries=entries, limit=10)

    assert result == "<@111> (Alice): first\n\n<@111> (Alice): second"


def test_render_exchange_limit_keeps_the_most_recent_n_oldest_first():
    entries = [
        (NOW - timedelta(minutes=5), "user", "<@111> (Alice): oldest"),
        (NOW - timedelta(minutes=3), "user", "<@111> (Alice): middle"),
        (NOW - timedelta(minutes=1), "user", "<@111> (Alice): newest"),
    ]

    result = render_exchange(entries=entries, limit=2)

    assert result == "<@111> (Alice): middle\n\n<@111> (Alice): newest"


def test_render_exchange_renders_user_verbatim_and_assistant_with_prefix():
    entries = [
        (NOW - timedelta(minutes=2), "user", "<@111> (Alice): hi"),
        (NOW - timedelta(minutes=1), "assistant", "hello there"),
    ]

    result = render_exchange(entries=entries, limit=10)

    assert "<@111> (Alice): hi" in result
    assert "Assistant:\nhello there" in result


def test_render_exchange_appends_assistant_reply_last_and_ignores_limit():
    entries = [
        (NOW - timedelta(minutes=5), "user", "<@111> (Alice): oldest"),
        (NOW - timedelta(minutes=3), "user", "<@111> (Alice): middle"),
        (NOW - timedelta(minutes=1), "user", "<@111> (Alice): newest"),
    ]

    result = render_exchange(entries=entries, limit=1, assistant_reply="the reply")

    assert result == "<@111> (Alice): newest\n\nAssistant:\nthe reply"


def test_render_exchange_empty_entries_with_and_without_reply():
    assert render_exchange(entries=[], limit=10, assistant_reply="the reply") == "Assistant:\nthe reply"
    assert render_exchange(entries=[], limit=10) == ""
