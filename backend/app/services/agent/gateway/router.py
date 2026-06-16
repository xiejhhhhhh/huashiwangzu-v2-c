import json
import logging
from pathlib import Path
from typing import AsyncGenerator
from .base import BaseProvider
from .opencode_provider import OpenCodeProvider
from .openai_provider import OpenAIProvider
from .local import LocalProvider
from .adapters import get_adapter
from app.core.defaults import DEFAULT_AGENT_MODEL

logger = logging.getLogger("v2.agent.gateway")

# ── Load model configuration from models.json ──────────────────────────
_MODELS_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "data" / "config" / "models.json"
)

_CONFIG: dict | None = None


def _load_models_config() -> dict:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    if not _MODELS_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"models.json not found at {_MODELS_CONFIG_PATH}. "
            f"Create it from the template in the task doc."
        )
    with open(_MODELS_CONFIG_PATH, "r") as f:
        _CONFIG = json.load(f)
    return _CONFIG


_config = _load_models_config()

# Build MODEL_PROFILES from config (keep interface for existing consumers)
MODEL_PROFILES: dict[str, dict] = _config["model_types"]["llm"]["profiles"]


class ModelGatewayRouter:
    def __init__(self):
        providers_config = _config.get("providers", {})
        self._providers: dict[str, BaseProvider] = {}
        for name, cfg in providers_config.items():
            ptype = cfg.get("type", "")
            if ptype == "opencode":
                self._providers[name] = OpenCodeProvider(
                    api_url=cfg.get("api_url", ""),
                )
            elif ptype == "openai_compat":
                self._providers[name] = OpenAIProvider(
                    api_url=cfg.get("api_url", ""),
                    provider_name=cfg.get("provider_name", name),
                )
            elif ptype == "local":
                self._providers[name] = LocalProvider()

    def get_profile(self, profile_key: str) -> dict:
        return MODEL_PROFILES.get(profile_key, MODEL_PROFILES[DEFAULT_AGENT_MODEL])

    def list_profiles(self) -> list[dict]:
        return [
            {"key": k, "name": k, "provider": v["provider"], "model": v["model"]}
            for k, v in MODEL_PROFILES.items()
        ]

    def get_provider(self, provider_name: str) -> BaseProvider:
        provider = self._providers.get(provider_name)
        if not provider:
            return self._providers["local"]
        return provider

    async def chat(
        self,
        messages: list[dict],
        profile_key: str = DEFAULT_AGENT_MODEL,
        tools: list[dict] | None = None,
    ) -> dict:
        profile = self.get_profile(profile_key)
        if profile["provider"] == "llama":
            await _ensure_local_text_model(profile)
        provider = self.get_provider(profile["provider"])
        raw = await provider.chat(
            messages=messages,
            model=profile["model"],
            temperature=profile["temperature"],
            max_tokens=profile["max_tokens"],
            tools=tools,
        )
        if "error" in raw:
            return raw
        if profile["provider"] in ("local",):
            return raw
        adapter = get_adapter(profile["model"])
        return adapter.adapt_response(raw, provider=profile["provider"])

    async def chat_stream(
        self,
        messages: list[dict],
        profile_key: str = DEFAULT_AGENT_MODEL,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        profile = self.get_profile(profile_key)
        if profile["provider"] == "llama":
            await _ensure_local_text_model(profile)
        provider = self.get_provider(profile["provider"])
        async for event in provider.chat_stream(
            messages=messages,
            model=profile["model"],
            temperature=profile["temperature"],
            max_tokens=profile["max_tokens"],
            tools=tools,
        ):
            yield event

    async def check_all_health(self) -> dict[str, bool]:
        result = {}
        for name, provider in self._providers.items():
            try:
                result[name] = await provider.check_health()
            except Exception as e:
                logger.warning("Health check failed for %s: %s", name, e)
                result[name] = False
        return result


gateway_router = ModelGatewayRouter()


async def _ensure_local_text_model(profile: dict | None = None) -> None:
    from asyncio import to_thread
    from app.services.model_watchdog.watchdog import ensure_model
    watchdog_name = (profile or {}).get("watchdog", "gemma-4")
    await to_thread(ensure_model, watchdog_name)


async def route_and_send(
    model_id: str,
    messages: list[dict],
    response_format: type | None = None,
    temperature: float = 0.7,
) -> dict | object:
    profile = MODEL_PROFILES.get(model_id, MODEL_PROFILES[DEFAULT_AGENT_MODEL]).copy()
    profile["temperature"] = temperature
    if profile["provider"] == "llama":
        await _ensure_local_text_model(profile)
    raw = await gateway_router.get_provider(profile["provider"]).chat(
        messages=messages,
        model=profile["model"],
        temperature=profile["temperature"],
        max_tokens=profile["max_tokens"],
    )
    if "error" in raw:
        raise RuntimeError(raw.get("content") or raw.get("error"))
    result = get_adapter(profile["model"]).adapt_response(raw, provider=profile["provider"])
    content = result.get("content", "")
    if response_format is None:
        return result
    import json
    payload = json.loads(content)
    return response_format(**payload)
