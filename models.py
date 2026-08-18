VISION_MODEL_TAGS = ("chat-latest", "claude", "gemini", "gemma", "gpt-4", "gpt-5", "gpt-latest", "grok-4", "llama", "vision", "vl")


def parse_provider_model(provider_slash_model: str) -> tuple[str, str]:
    provider, model = provider_slash_model.removesuffix(":vision").split("/", 1)
    return provider, model


def accepts_images(provider_slash_model: str, vision_tags: tuple[str, ...] = VISION_MODEL_TAGS) -> bool:
    return any(x in provider_slash_model.lower() for x in vision_tags)
