from permissions import is_allowed


def _permissions(
    admin_ids=None,
    allowed_user_ids=None,
    blocked_user_ids=None,
    allowed_role_ids=None,
    blocked_role_ids=None,
    allowed_channel_ids=None,
    blocked_channel_ids=None,
):
    return {
        "users": {
            "admin_ids": list(admin_ids or []),
            "allowed_ids": list(allowed_user_ids or []),
            "blocked_ids": list(blocked_user_ids or []),
        },
        "roles": {
            "allowed_ids": list(allowed_role_ids or []),
            "blocked_ids": list(blocked_role_ids or []),
        },
        "channels": {
            "allowed_ids": list(allowed_channel_ids or []),
            "blocked_ids": list(blocked_channel_ids or []),
        },
    }


def test_empty_allow_lists_permit_an_ordinary_user_in_a_guild():
    permissions = _permissions()

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids={10},
            permissions=permissions,
            is_dm=False,
            allow_dms=True,
        )
        is True
    )


def test_empty_allow_lists_permit_an_ordinary_user_in_a_dm():
    permissions = _permissions()

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids=set(),
            permissions=permissions,
            is_dm=True,
            allow_dms=True,
        )
        is True
    )


def test_blocked_user_is_rejected_even_when_admin():
    permissions = _permissions(admin_ids=[1], blocked_user_ids=[1])

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids={10},
            permissions=permissions,
            is_dm=False,
            allow_dms=True,
        )
        is False
    )


def test_user_with_blocked_role_is_rejected():
    permissions = _permissions(blocked_role_ids=[100])

    assert (
        is_allowed(
            user_id=1,
            role_ids={100},
            channel_ids={10},
            permissions=permissions,
            is_dm=False,
            allow_dms=True,
        )
        is False
    )


def test_admin_is_permitted_when_allowed_ids_non_empty_and_excludes_them():
    permissions = _permissions(admin_ids=[1], allowed_user_ids=[2])

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids={10},
            permissions=permissions,
            is_dm=False,
            allow_dms=True,
        )
        is True
    )


def test_non_admin_non_listed_user_is_rejected_when_allowed_ids_non_empty():
    permissions = _permissions(allowed_user_ids=[2])

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids={10},
            permissions=permissions,
            is_dm=False,
            allow_dms=True,
        )
        is False
    )


def test_user_is_permitted_via_an_allowed_role():
    permissions = _permissions(allowed_role_ids=[100])

    assert (
        is_allowed(
            user_id=1,
            role_ids={100},
            channel_ids={10},
            permissions=permissions,
            is_dm=False,
            allow_dms=True,
        )
        is True
    )


def test_dm_with_allow_dms_false_rejects_non_admin():
    permissions = _permissions()

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids=set(),
            permissions=permissions,
            is_dm=True,
            allow_dms=False,
        )
        is False
    )


def test_dm_with_allow_dms_false_still_permits_admin():
    permissions = _permissions(admin_ids=[1])

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids=set(),
            permissions=permissions,
            is_dm=True,
            allow_dms=False,
        )
        is True
    )


def test_dm_ignores_channel_allowed_ids_that_exclude_the_channel():
    permissions = _permissions(allowed_channel_ids=[999])

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids={10},
            permissions=permissions,
            is_dm=True,
            allow_dms=True,
        )
        is True
    )


def test_guild_blocked_channel_id_rejects():
    permissions = _permissions(blocked_channel_ids=[10])

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids={10},
            permissions=permissions,
            is_dm=False,
            allow_dms=True,
        )
        is False
    )


def test_guild_blocked_parent_or_category_id_in_channel_ids_rejects():
    permissions = _permissions(blocked_channel_ids=[20])

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids={10, 20},
            permissions=permissions,
            is_dm=False,
            allow_dms=True,
        )
        is False
    )


def test_guild_with_non_empty_channel_allowed_ids_rejects_channel_not_in_list():
    permissions = _permissions(allowed_channel_ids=[999])

    assert (
        is_allowed(
            user_id=1,
            role_ids=set(),
            channel_ids={10},
            permissions=permissions,
            is_dm=False,
            allow_dms=True,
        )
        is False
    )
