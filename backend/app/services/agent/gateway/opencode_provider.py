from app.config import get_settings
from .openai_provider import OpenAIProvider

OPENCODE_API_URL = "https://opencode.ai/zen/go/v1/chat/completions"


class OpenCodeProvider(OpenAIProvider):
    def __init__(self, api_url: str = "", api_key: str = ""):
        super().__init__(
            api_url=api_url or OPENCODE_API_URL,
            api_key=api_key or get_settings().DEEPSEEK_API_KEY,
            provider_name="opencode",
        )
