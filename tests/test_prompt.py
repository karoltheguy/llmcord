from datetime import datetime

from prompt import MEMORY_HEADER, build_memory_blocks, build_system_prompt, render_claim_line
from memory_store import Claim


def test_returns_substituted_prompt_when_no_memory():
    now = datetime(2026, 1, 2, 3, 4, 5)
    system_prompt = "You are a helpful assistant. Today is {date} and current time is {time}."
    expected = system_prompt.replace("{date}", now.strftime("%B %d %Y")).replace("{time}", now.strftime("%H:%M:%S %Z%z")).strip()
    result = build_system_prompt(system_prompt, now)
    assert result == expected


def test_returns_none_without_system_prompt():
    now = datetime(2026, 1, 2, 3, 4, 5)
    assert build_system_prompt(None, now) is None
    assert build_system_prompt("", now) is None


def test_memory_blocks_are_appended_in_a_byte_identical_block():
    now = datetime(2026, 1, 2, 3, 4, 5)
    system_prompt = "You are a helpful assistant."
    result = build_system_prompt(system_prompt, now, memory_blocks=["likes cats"])
    expected = f"You are a helpful assistant.\n\n<user_memory>\n{MEMORY_HEADER}\nlikes cats\n</user_memory>"
    assert result == expected


def test_empty_memory_blocks_return_bare_prompt():
    now = datetime(2026, 1, 2, 3, 4, 5)
    system_prompt = "You are a helpful assistant."
    for blocks in (None, [], [""], ["", "   "]):
        result = build_system_prompt(system_prompt, now, memory_blocks=blocks)
        assert result == system_prompt
        assert "<user_memory>" not in result


def test_multiple_memory_blocks_joined_in_one_element():
    now = datetime(2026, 1, 2, 3, 4, 5)
    system_prompt = "You are a helpful assistant."
    blocks = ["block one", "block two", "block three"]
    result = build_system_prompt(system_prompt, now, memory_blocks=blocks)
    assert result.count("<user_memory>") == 1
    assert result.count("</user_memory>") == 1
    assert result.count(MEMORY_HEADER) == 1
    assert "block one\n\nblock two\n\nblock three" in result
    assert result.index("block one") < result.index("block two") < result.index("block three")


def test_max_memory_text_truncates_each_block_independently():
    now = datetime(2026, 1, 2, 3, 4, 5)
    system_prompt = "You are a helpful assistant."
    blocks = ["a" * 50, "b" * 50]
    result = build_system_prompt(system_prompt, now, memory_blocks=blocks, max_memory_text=10)
    assert "a" * 10 in result
    assert "a" * 11 not in result
    assert "b" * 10 in result
    assert "b" * 11 not in result


def test_max_memory_total_drops_blocks_from_the_tail():
    now = datetime(2026, 1, 2, 3, 4, 5)
    system_prompt = "You are a helpful assistant."
    blocks = ["first block text", "second block text", "third block text"]
    result = build_system_prompt(system_prompt, now, memory_blocks=blocks, max_memory_total=30)
    assert "first block text" in result
    assert "third block text" not in result


def test_render_claim_line_with_two_named_subjects():
    result = render_claim_line({222, 333}, {222: "Bob", 333: "Carol"}, "they had a fight at the party")
    assert result == "- about <@222> (Bob), <@333> (Carol): they had a fight at the party"


def test_render_claim_line_unnamed_subject_fallback():
    result = render_claim_line({222}, {}, "likes cats")
    assert result == "- about <@222>: likes cats"


def test_build_memory_blocks_orders_self_then_claims_then_others():
    author_id = 111
    names = {111: "Alice", 222: "Bob", 333: "Carol"}
    author_memory = "Author self memory"
    author_claims = [
        Claim(id=1, source_id=111, subjects={222}, text="claim from author", created_at="2026-01-01T00:00:00"),
    ]
    other_memories = {222: "Bob's memory", 333: None}
    other_claims = [
        Claim(id=2, source_id=222, subjects={111}, text="claim from bob", created_at="2026-01-02T00:00:00"),
    ]
    blocks = build_memory_blocks(
        names=names,
        author_memory=author_memory,
        author_claims=author_claims,
        other_memories=other_memories,
        other_claims=other_claims,
    )
    assert blocks[0] == "Author self memory"
    assert any("said:" in b for b in blocks[1:-1])
    assert blocks[-1] == "About <@222> (Bob):\nBob's memory"


def test_build_memory_blocks_groups_claims_by_speaker():
    claims = [
        Claim(id=1, source_id=222, subjects={111}, text="first claim", created_at="2026-01-01T00:00:00"),
        Claim(id=2, source_id=222, subjects={333}, text="second claim", created_at="2026-01-02T00:00:00"),
    ]
    blocks = build_memory_blocks(
        names={111: "Alice", 222: "Bob", 333: "Carol"},
        author_memory=None,
        author_claims=[],
        other_memories={},
        other_claims=claims,
    )
    claim_blocks = [b for b in blocks if b.startswith("<@222")]
    assert len(claim_blocks) == 1
    assert "first claim" in claim_blocks[0]
    assert "second claim" in claim_blocks[0]


def test_build_memory_blocks_omits_falsy_author_memory():
    blocks = build_memory_blocks(
        names={},
        author_memory=None,
        author_claims=[],
        other_memories={},
        other_claims=[],
    )
    assert "" not in blocks
    assert blocks == []
