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
from app.gateway.config import DEFAULT_MODEL

logger = logging.getLogger("v2.gateway.router")
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0
RETRYABLE_STATUSES = {429, 502, 503, 504}

# ── Load model configuration from models.json ──────────────────────────
_MODELS_CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "config" / "models.json"
)

_CONFIG: dict | None = None


def _load_models_config() -> dict:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    if not _MODELS_CONFIG_PATH.exists():
        logger.warning("models.json not found at %s, gateway will use empty config", _MODELS_CONFIG_PATH)
        _CONFIG = {"providers": {}, "model_types": {"llm": {"profiles": {}}}}
        return _CONFIG
    with open(_MODELS_CONFIG_PATH, "r") as f:
        _CONFIG = json.load(f)
    return _CONFIG


_config = _load_models_config()

# Build MODEL_PROFILES from config (keep interface for existing consumers)
MODEL_PROFILES: dict[str, dict] = _config["model_types"]["llm"]["profiles"]

# ── Vision profile loading ─────────────────────────────────────────────
_vision_cfg = _config.get("model_types", {}).get("vision", {})
_VISION_PRIMARY: str = _vision_cfg.get("primary", "mimo")
_VISION_FALLBACK: list[str] = _vision_cfg.get("fallback_chain", ["qwen3-vl"])
_VISION_PROFILES: dict[str, dict] = _vision_cfg.get("profiles", {})


def _resolve_api_key(provider_cfg: dict) -> str:
    """Read api_key from settings using provider config's api_key_env field."""
    env_name = provider_cfg.get("api_key_env", "")
    if not env_name:
        return ""
    from app.config import get_settings
    key = getattr(get_settings(), env_name, "")
    if not key:
        logger.warning("Provider config references %s but it is empty in settings", env_name)
    return key


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
                    api_key=_resolve_api_key(cfg),
                    provider_name=cfg.get("provider_name", name),
                )
            elif ptype == "local":
                self._providers[name] = LocalProvider()

    def get_profile(self, profile_key: str) -> dict:
        profile = MODEL_PROFILES.get(profile_key) or MODEL_PROFILES.get(DEFAULT_MODEL)
        if not profile:
            raise RuntimeError("No LLM model profiles configured in models.json")
        return profile

    def list_profiles(self) -> list[dict]:
        return [
            {"key": k, "name": k, "provider": v["provider"], "model": v["model"]}
            for k, v in MODEL_PROFILES.items()
        ]

    def get_provider(self, provider_name: str) -> BaseProvider:
        provider = self._providers.get(provider_name)
        if not provider:
            fallback = self._providers.get("local")
            if fallback:
                return fallback
            raise RuntimeError(f"Model provider '{provider_name}' is not configured")
        return provider

    async def chat(
        self,
        messages: list[dict],
        profile_key: str = DEFAULT_MODEL,
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
            detail = str(exc)
            # 尝试从 httpx.HTTPStatusError 中提取响应体
            if hasattr(exc, "response"):
                try:
                    body = exc.response.text
                    if body:
                        detail = f"{detail}\n响应体: {body[:1000]}"
                except Exception:
                    pass
            logger.error("AI gateway chat failed: %s", detail)
            return {"error": str(exc), "content": f"(Model error: {detail})"}
        if "error" in raw:
            return raw
        if profile["provider"] in ("local",):
            return raw
        adapter = get_adapter(profile["model"])
        return adapter.adapt_response(raw, provider=profile["provider"])

    async def chat_stream(
        self,
        messages: list[dict],
        profile_key: str = DEFAULT_MODEL,
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

    def _resolve_vision_profile(self, profile_key: str | None = None) -> dict:
        """Resolve vision profile key → profile dict, with fallback chain."""
        if profile_key and profile_key in _VISION_PROFILES:
            return _VISION_PROFILES[profile_key]
        if _VISION_PRIMARY and _VISION_PRIMARY in _VISION_PROFILES:
            return _VISION_PROFILES[_VISION_PRIMARY]
        for fb in _VISION_FALLBACK:
            if fb in _VISION_PROFILES:
                return _VISION_PROFILES[fb]
        raise RuntimeError("No vision model profiles configured in models.json")

    async def describe_image(
        self,
        image_bytes: bytes,
        prompt: str = "请详细描述这张图片",
        profile_key: str | None = None,
        mime_type: str = "image/jpeg",
    ) -> str:
        """Describe an image using the configured vision model, with fallback chain.

        Returns the text description from the vision model.
        Falls back through _VISION_FALLBACK if the primary model fails.
        """
        import base64
        b64 = base64.b64encode(image_bytes).decode("ascii")
        img_data_url = f"data:{mime_type};base64,{b64}"
        messages = [
            {"role": "system", "content": "You are an image description assistant. Describe the image in Chinese in 1-3 sentences, focusing on visual content."},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": img_data_url, "detail": "high"}},
                {"type": "text", "text": prompt},
            ]},
        ]

        # Try primary → fallback chain
        candidate_keys = [profile_key] if profile_key else [_VISION_PRIMARY] + _VISION_FALLBACK
        last_error = None
        for idx, key in enumerate(candidate_keys):
            profile = _VISION_PROFILES.get(key)
            if not profile:
                continue
            try:
                if profile.get("provider") == "llama":
                    await _ensure_local_vision_model(profile)
                provider = self.get_provider(profile["provider"])
                raw = await _call_with_retry(
                    provider=provider,
                    messages=messages,
                    model=profile.get("model", key),
                    temperature=profile.get("temperature", 0.7),
                    max_tokens=profile.get("max_tokens", 4096),
                    tools=None,
                )
                if "error" in raw:
                    raise RuntimeError(raw.get("content") or raw.get("error"))
                if profile.get("provider") in ("local",):
                    return raw.get("content", "")
                adapter = get_adapter(profile.get("model", key))
                result = adapter.adapt_response(raw, provider=profile.get("provider", ""))
                content = (result.get("content") or "").strip()
                if content:
                    return content
            except Exception as exc:
                logger.warning("Vision model %s failed (attempt %d/%d): %s", key, idx + 1, len(candidate_keys), exc)
                last_error = exc
                continue
        raise RuntimeError(f"All vision models failed. Last error: {last_error}")

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


async def _ensure_local_vision_model(profile: dict) -> None:
    """Ensure a local vision model (e.g. qwen3-vl) is running via watchdog."""
    from asyncio import to_thread
    from app.services.model_watchdog.watchdog import ensure_model
    watchdog_name = profile.get("watchdog", "qwen3-vl")
    await to_thread(ensure_model, watchdog_name)


async def route_and_send(
    model_id: str,
    messages: list[dict],
    response_format: type | None = None,
    temperature: float = 0.7,
) -> dict | object:
    profile = MODEL_PROFILES.get(model_id, MODEL_PROFILES[DEFAULT_MODEL]).copy()
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
