import asyncio
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
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0
RETRYABLE_STATUSES = {429, 502, 503, 504}

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


def _status_code_from_exception(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    return status if isinstance(status, int) else None


def _is_retryable_exception(exc: Exception) -> bool:
    status_code = _status_code_from_exception(exc)
    if status_code in RETRYABLE_STATUSES:
        return True
    return isinstance(exc, (ConnectionError, TimeoutError, asyncio.TimeoutError))


async def _call_with_retry(
    provider: BaseProvider,
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    tools: list[dict] | None,
) -> dict:
    for attempt_index in range(RETRY_MAX_ATTEMPTS):
        try:
            return await provider.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )
        except Exception as exc:
            if not _is_retryable_exception(exc) or attempt_index == RETRY_MAX_ATTEMPTS - 1:
                raise
            delay = RETRY_BASE_DELAY_SECONDS * (2 ** attempt_index)
            logger.warning(
                "AI gateway call attempt %d/%d failed (status=%s), retrying in %.1fs",
                attempt_index + 1,
                RETRY_MAX_ATTEMPTS,
                _status_code_from_exception(exc),
                delay,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("AI gateway retry loop exhausted")


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
        try:
            raw = await _call_with_retry(
                provider=provider,
                messages=messages,
                model=profile["model"],
                temperature=profile["temperature"],
                max_tokens=profile["max_tokens"],
                tools=tools,
            )
        except Exception as exc:
            logger.error("AI gateway chat failed: %s", exc)
            return {"error": str(exc), "content": f"(Model error: {exc})"}
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
    raw = await _call_with_retry(
        provider=gateway_router.get_provider(profile["provider"]),
        messages=messages,
        model=profile["model"],
        temperature=profile["temperature"],
        max_tokens=profile["max_tokens"],
        tools=None,
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
