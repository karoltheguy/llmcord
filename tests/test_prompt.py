from datetime import datetime

from prompt import build_system_prompt


def test_returns_substituted_prompt_when_no_memory():
    now = datetime(2026, 1, 2, 3, 4, 5)
    system_prompt = "You are a helpful assistant. Today is {date} and current time is {time}."
    expected = system_prompt.replace("{date}", now.strftime("%B %d %Y")).replace("{time}", now.strftime("%H:%M:%S %Z%z")).strip()
    result = build_system_prompt(system_prompt, now, memory=None)
    assert result == expected


def test_empty_memory_is_identical_to_no_memory():
    now = datetime(2026, 1, 2, 3, 4, 5)
    system_prompt = "You are a helpful assistant. Today is {date} and current time is {time}."
    result_none = build_system_prompt(system_prompt, now, memory=None)
    result_empty = build_system_prompt(system_prompt, now, memory="")
    assert result_empty == result_none


def test_memory_is_appended_in_a_delimited_block():
    now = datetime(2026, 1, 2, 3, 4, 5)
    system_prompt = "You are a helpful assistant."
    result = build_system_prompt(system_prompt, now, memory="likes cats")
    assert result.startswith("You are a helpful assistant.")
    assert "<user_memory>" in result
    assert "likes cats" in result
    assert "</user_memory>" in result
    assert result.index("You are a helpful assistant.") < result.index("<user_memory>") < result.index("likes cats") < result.index("</user_memory>")


def test_memory_is_truncated_to_budget():
    now = datetime(2026, 1, 2, 3, 4, 5)
    system_prompt = "You are a helpful assistant."
    result = build_system_prompt(system_prompt, now, memory="x" * 500, max_memory_text=10)
    assert "x" * 10 in result
    assert "x" * 11 not in result


def test_returns_none_without_system_prompt():
    now = datetime(2026, 1, 2, 3, 4, 5)
    assert build_system_prompt(None, now, memory="likes cats") is None
    assert build_system_prompt("", now) is None
