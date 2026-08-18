from typing import Any


def is_user_allowed(*, user_id: int, role_ids: set[int], permissions: dict[str, Any], is_dm: bool) -> bool:
    user_is_admin = user_id in permissions["users"]["admin_ids"]

    allowed_user_ids, blocked_user_ids = permissions["users"]["allowed_ids"], permissions["users"]["blocked_ids"]
    allowed_role_ids, blocked_role_ids = permissions["roles"]["allowed_ids"], permissions["roles"]["blocked_ids"]

    allow_all_users = not allowed_user_ids if is_dm else not allowed_user_ids and not allowed_role_ids
    is_good_user = user_is_admin or allow_all_users or user_id in allowed_user_ids or any(id in allowed_role_ids for id in role_ids)
    is_bad_user = not is_good_user or user_id in blocked_user_ids or any(id in blocked_role_ids for id in role_ids)

    return not is_bad_user


def is_channel_allowed(*, user_id: int, channel_ids: set[int], permissions: dict[str, Any], is_dm: bool, allow_dms: bool) -> bool:
    user_is_admin = user_id in permissions["users"]["admin_ids"]

    allowed_channel_ids, blocked_channel_ids = permissions["channels"]["allowed_ids"], permissions["channels"]["blocked_ids"]

    allow_all_channels = not allowed_channel_ids
    is_good_channel = (user_is_admin or allow_dms) if is_dm else (allow_all_channels or any(id in allowed_channel_ids for id in channel_ids))
    is_bad_channel = not is_good_channel or any(id in blocked_channel_ids for id in channel_ids)

    return not is_bad_channel


def is_allowed(*, user_id: int, role_ids: set[int], channel_ids: set[int], permissions: dict[str, Any], is_dm: bool, allow_dms: bool) -> bool:
    return is_user_allowed(user_id=user_id, role_ids=role_ids, permissions=permissions, is_dm=is_dm) and is_channel_allowed(
        user_id=user_id, channel_ids=channel_ids, permissions=permissions, is_dm=is_dm, allow_dms=allow_dms
    )
