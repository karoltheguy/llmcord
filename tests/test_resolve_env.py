from config import resolve_env


def test_key_ending_in_env_is_replaced_by_environment_variable_value(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "shh")

    result = resolve_env({"api_key_env": "MY_SECRET"})

    assert result == {"api_key": "shh"}


def test_unset_environment_variable_resolves_to_none(monkeypatch):
    monkeypatch.delenv("UNSET_VARIABLE", raising=False)

    result = resolve_env({"api_key_env": "UNSET_VARIABLE"})

    assert result == {"api_key": None}


def test_plain_key_without_suffix_is_left_untouched():
    result = resolve_env({"api_key": "literal-value"})

    assert result == {"api_key": "literal-value"}


def test_nested_dicts_are_resolved_recursively(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "shh")

    result = resolve_env({"outer": {"inner_env": "MY_SECRET", "plain": "value"}})

    assert result == {"outer": {"inner": "shh", "plain": "value"}}


def test_list_value_is_returned_unchanged():
    result = resolve_env({"items": ["a_env", "b"]})

    assert result == {"items": ["a_env", "b"]}


def test_non_dict_scalar_input_is_returned_unchanged():
    assert resolve_env("just a string") == "just a string"
    assert resolve_env(42) == 42
    assert resolve_env(None) is None
