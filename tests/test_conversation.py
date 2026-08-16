from conversation import should_chain_to_previous


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
