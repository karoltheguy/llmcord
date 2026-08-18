from models import VISION_MODEL_TAGS, accepts_images, parse_provider_model


def test_parse_strips_vision_suffix_and_splits():
    assert parse_provider_model("openai/gpt-5:vision") == ("openai", "gpt-5")


def test_parse_without_vision_suffix():
    assert parse_provider_model("openai/gpt-5") == ("openai", "gpt-5")


def test_parse_keeps_additional_slashes_in_model_half():
    assert parse_provider_model("ollama/library/llama3") == ("ollama", "library/llama3")


def test_accepts_images_true_for_tagged_model():
    assert accepts_images("openai/gpt-5") is True


def test_accepts_images_false_for_untagged_model():
    assert accepts_images("mistral/mistral-small") is False


def test_accepts_images_true_because_of_vision_suffix_on_untagged_model():
    assert accepts_images("mistral/mistral-small:vision") is True


def test_accepts_images_is_case_insensitive():
    assert accepts_images("OpenAI/GPT-5") is True


def test_vision_model_tags_exact_value():
    assert VISION_MODEL_TAGS == (
        "chat-latest",
        "claude",
        "gemini",
        "gemma",
        "gpt-4",
        "gpt-5",
        "gpt-latest",
        "grok-4",
        "llama",
        "vision",
        "vl",
    )
