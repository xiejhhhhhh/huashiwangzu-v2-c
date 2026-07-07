from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import AsyncGenerator

from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt
from tenacity.wait import wait_base

from app.gateway.config import (
    DEFAULT_MODEL,
    MODEL_PROFILES,
    get_models_config,
    get_model_type_config,
    get_provider_configs,
)
from app.gateway.protocol import is_protocol_error_text
from app.gateway.vision_preprocess import (
    messages_contain_image_payload,
    prepare_vision_image_for_model,
    prepare_vision_image_for_model_from_config,
)

from .adapters import _extract_usage, get_adapter
from .base import BaseProvider
from .contract import (
    ModelRequest,
    ModelResponse,
    model_request_from_dict,
    model_response_to_dict,
)
from .error_classifier import classify_error, compute_delay
from .local import LocalProvider
from .openai_provider import OpenAIProvider, OpenCodeProvider
from .usage_tracker import UsageRecord, log_usage, log_usage_event

logger = logging.getLogger("v2.gateway.router")
_prepare_vision_image_for_model = prepare_vision_image_for_model


@dataclass
class RetryBudget:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    strategy: str = "exponential"
    max_delay_seconds: float = 60.0


def _retry_budget_from_profile(profile: dict, override: RetryBudget | None) -> RetryBudget | None:
    if override is not None:
        return override
    if not any(key in profile for key in ("retry_max_attempts", "retry_delay_seconds", "retry_strategy")):
        return None
    return RetryBudget(
        max_attempts=int(profile.get("retry_max_attempts", 3)),
        base_delay_seconds=float(profile.get("retry_delay_seconds", 1.0)),
        strategy=str(profile.get("retry_strategy", "exponential")),
    )


def _retry_delay(classification, attempt_index: int, budget: RetryBudget) -> float:
    if budget.strategy == "fixed" and classification.retry_after is None:
        return max(0.1, min(budget.base_delay_seconds, budget.max_delay_seconds))
    return compute_delay(
        classification,
        attempt_index,
        budget.base_delay_seconds,
        max_delay=budget.max_delay_seconds,
    )


class _RetryableGatewayError(Exception):
    def __init__(self, original: Exception, attempt_index: int, delay_seconds: float) -> None:
        super().__init__(str(original))
        self.original = original
        self.attempt_index = attempt_index
        self.delay_seconds = delay_seconds


class _GatewayRetryWait(wait_base):
    def __call__(self, retry_state: RetryCallState) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(exc, _RetryableGatewayError):
            return exc.delay_seconds
        return 0.0


# ── Vision profile loading ─────────────────────────────────────────────
_vision_cfg = get_model_type_config("vision")
_VISION_PRIMARY: str = str(_vision_cfg.get("primary") or "")
_VISION_FALLBACK: list[str] = (
    list(_vision_cfg.get("fallback_chain") or [])
    if isinstance(_vision_cfg.get("fallback_chain"), list)
    else []
)
_VISION_PROFILES: dict[str, dict] = (
    _vision_cfg.get("profiles", {})
    if isinstance(_vision_cfg.get("profiles", {}), dict)
    else {}
)


def _profile_chain_for_model_type(
    model_type: str,
    requested_key: str | None,
    *,
    primary_key: str | None = None,
    fallback_chain: list[str] | None = None,
    profiles: dict[str, dict] | None = None,
) -> list[str]:
    """Return ordered profile candidates from models.json.

    The requested profile is tried first.  When
    ``fallback_on_explicit_profile`` is enabled (default), explicitly asking for
    a cloud profile such as ``mimo`` or ``deepseek-v4-flash`` still falls back to
    the configured local chain when the provider is unavailable or out of quota.
    """
    cfg = get_model_type_config(model_type)
    profile_map = profiles if profiles is not None else cfg.get("profiles", {})
    configured_primary = primary_key or cfg.get("primary")
    primary = str(configured_primary or (DEFAULT_MODEL if model_type == "llm" else ""))
    if not profile_map or not primary:
        return []
    requested = requested_key if requested_key in profile_map else primary
    fallback_enabled = bool(cfg.get("fallback_on_explicit_profile", True))
    raw_fallbacks = fallback_chain if fallback_chain is not None else cfg.get("fallback_chain", [])
    requested_profile = profile_map.get(requested) if requested in profile_map else None
    if isinstance(requested_profile, dict):
        fallback_policy = requested_profile.get("fallback_policy")
        fallback_policies = get_models_config().get("fallback_policies", {})
        if fallback_policy and isinstance(fallback_policies, dict):
            configured_policy = fallback_policies.get(str(fallback_policy))
            if isinstance(configured_policy, list):
                raw_fallbacks = configured_policy
            elif isinstance(configured_policy, dict) and isinstance(configured_policy.get("chain"), list):
                raw_fallbacks = configured_policy["chain"]
        elif isinstance(requested_profile.get("fallback_chain"), list):
            raw_fallbacks = requested_profile["fallback_chain"]
        elif requested_profile.get("fallback_profile"):
            raw_fallbacks = [str(requested_profile["fallback_profile"])]

    chain = [requested]
    if fallback_enabled:
        chain.extend(raw_fallbacks or [])

    result: list[str] = []
    seen: set[str] = set()
    for key in chain:
        if not key or key in seen or key not in profile_map:
            continue
        seen.add(key)
        result.append(key)
    return result


def _resolve_api_key(provider_cfg: dict) -> str:
    env_name = provider_cfg.get("api_key_env", "")
    if not env_name:
        return ""
    from app.config import get_settings
    key = getattr(get_settings(), env_name, "")
    if not key:
        logger.warning("Provider config references %s but it is empty in settings", env_name)
    return key


async def _call_with_unified_retry(
    provider: BaseProvider,
    req: ModelRequest,
    model: str,
    caller_module: str,
    profile_key: str,
    provider_name: str,
    budget: RetryBudget | None = None,
) -> ModelResponse:
    b = budget or RetryBudget()
    last_error: Exception | None = None

    retrying = AsyncRetrying(
        stop=stop_after_attempt(b.max_attempts),
        retry=retry_if_exception(lambda exc: isinstance(exc, _RetryableGatewayError)),
        wait=_GatewayRetryWait(),
        reraise=True,
    )

    try:
        async for attempt in retrying:
            attempt_index = attempt.retry_state.attempt_number - 1
            start_time = time.monotonic()
            duration_ms = 0.0
            raw = None
            with attempt:
                try:
                    raw = await provider.chat(
                        messages=req.messages,
                        model=model,
                        temperature=req.temperature,
                        max_tokens=req.max_tokens,
                        tools=req.tools,
                    )
                    duration_ms = (time.monotonic() - start_time) * 1000
                except Exception as exc:
                    duration_ms = (time.monotonic() - start_time) * 1000
                    classification = classify_error(exception=exc)
                    last_error = exc

                    log_usage_event(UsageRecord(
                        model_key=profile_key,
                        provider_name=provider_name,
                        caller_module=caller_module,
                        duration_ms=duration_ms,
                        success=False,
                        error_category=classification.category,
                    ))

                    if not classification.retryable or attempt_index == b.max_attempts - 1:
                        detail = _format_exception_detail(exc)
                        logger.error("AI gateway call failed (non-retryable): %s", detail)
                        return ModelResponse(
                            content=f"(Model error: {detail})",
                            error=detail,
                            finish_reason="error",
                        )

                    delay = _retry_delay(classification, attempt_index, b)
                    logger.warning(
                        "AI gateway call attempt %d/%d failed (profile=%s provider=%s model=%s category=%s strategy=%s), retrying in %.1fs",
                        attempt_index + 1,
                        b.max_attempts,
                        profile_key,
                        provider_name,
                        model,
                        classification.category,
                        b.strategy,
                        delay,
                    )
                    raise _RetryableGatewayError(exc, attempt_index, delay)

            if raw is None:
                continue

            if "error" in raw:
                error = str(raw.get("error"))
                return ModelResponse(
                    content=f"(Provider error: {raw.get('error')})",
                    error=error,
                    finish_reason="error",
                )

            usage = _extract_usage(raw)

            if usage and (usage.prompt_tokens > 0 or usage.completion_tokens > 0):
                await log_usage(
                    model_key=profile_key,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    provider_name=provider_name,
                    caller_module=caller_module,
                    duration_ms=duration_ms,
                    success=True,
                )

            log_usage_event(UsageRecord(
                model_key=profile_key,
                provider_name=provider_name,
                caller_module=caller_module,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                duration_ms=duration_ms,
                success=True,
            ))

            if provider_name == "local":
                return ModelResponse(
                    content=raw.get("content", ""),
                    thinking=raw.get("thinking", ""),
                    tool_calls=[],
                    finish_reason=raw.get("finish_reason", "stop"),
                )

            adapter = get_adapter(model)
            result = adapter.adapt_response(raw, provider=provider_name)

            if usage and not result.usage:
                result.usage = usage

            return result
    except _RetryableGatewayError as exc:
        last_error = exc.original

    if last_error is not None:
        detail = _format_exception_detail(last_error)
        logger.error("AI gateway call failed after retry exhaustion: %s", detail)
        return ModelResponse(
            content=f"(Model error: {detail})",
            error=detail,
            finish_reason="error",
        )

    return ModelResponse(
        content="(Retry exhausted)",
        error="All retry attempts failed",
        finish_reason="error",
    )


def _format_exception_detail(exc: Exception) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    if hasattr(exc, "response"):
        try:
            body = exc.response.text
            if body:
                detail = f"{detail}\n响应体: {body[:1000]}"
        except Exception:
            pass
    return detail


class ModelGatewayRouter:
    def __init__(self):
        providers_config = get_provider_configs()
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
                    extra_headers=cfg.get("headers") or {},
                    session_affinity=cfg.get("session_affinity") or {},
                    auth_recovery=cfg.get("auth_recovery") or {},
                )
            elif ptype == "local":
                self._providers[name] = LocalProvider(allow_echo=bool(cfg.get("allow_echo", False)))

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
        budget: RetryBudget | None = None,
    ) -> dict:
        if messages_contain_image_payload(messages):
            error = (
                "Image payloads must use gateway.describe_image_detailed so the "
                "unified VLM image compression policy is always applied."
            )
            return {
                "content": f"(Gateway policy error: {error})",
                "error": error,
                "diagnostics": {
                    "requested_profile": profile_key,
                    "policy": "vision_images_must_use_describe_image",
                },
            }
        candidate_keys = _profile_chain_for_model_type("llm", profile_key, profiles=MODEL_PROFILES)
        diagnostics: dict = {
            "requested_profile": profile_key,
            "candidates": candidate_keys,
            "attempts": [],
            "fallback_used": False,
        }
        last_result: ModelResponse | None = None
        last_key = profile_key

        for idx, key in enumerate(candidate_keys):
            profile = self.get_profile(key)
            if profile["provider"] == "llama":
                try:
                    await _ensure_local_text_model(profile)
                except Exception as exc:
                    detail = _format_exception_detail(exc)
                    diagnostics["attempts"].append({
                        "profile": key,
                        "provider": profile.get("provider", ""),
                        "model": profile.get("model", key),
                        "stage": "health",
                        "success": False,
                        "error": detail,
                    })
                    logger.warning(
                        "Local LLM profile %s failed health/startup, trying next fallback if any: %s",
                        key,
                        detail,
                    )
                    last_result = ModelResponse(
                        content=f"(Model error: {detail})",
                        error=detail,
                        finish_reason="error",
                    )
                    last_key = key
                    continue

            req = model_request_from_dict({
                "messages": messages,
                "tools": tools,
                "temperature": profile["temperature"],
                "max_tokens": profile["max_tokens"],
            })

            effective_budget = _retry_budget_from_profile(profile, budget)
            result = await _call_with_unified_retry(
                provider=self.get_provider(profile["provider"]),
                req=req,
                model=profile["model"],
                caller_module="gateway.chat",
                profile_key=key,
                provider_name=profile.get("provider", ""),
                budget=effective_budget,
            )
            diagnostics["attempts"].append({
                "profile": key,
                "provider": profile.get("provider", ""),
                "model": profile.get("model", key),
                "stage": "chat",
                "success": not bool(result.error),
                "error": result.error,
            })
            if not result.error:
                diagnostics["selected_profile"] = key
                diagnostics["selected_provider"] = profile.get("provider", "")
                diagnostics["fallback_used"] = idx > 0
                result.diagnostics = diagnostics
                if idx > 0:
                    logger.warning("LLM fallback succeeded: %s -> %s", last_key, key)
                return model_response_to_dict(result)

            last_result = result
            last_key = key
            classification = classify_error(body=result.error or result.content)
            if classification.category == "protocol" or is_protocol_error_text(classification.message):
                logger.error("LLM protocol error, fallback stopped: %s", result.error)
                result.diagnostics = diagnostics
                return model_response_to_dict(result)
            if idx < len(candidate_keys) - 1:
                logger.warning(
                    "LLM profile %s failed, trying fallback %s: %s",
                    key,
                    candidate_keys[idx + 1],
                    result.error,
                )

        if last_result is not None:
            last_result.content = f"(Model fallback exhausted: {last_result.error or last_result.content})"
            last_result.diagnostics = diagnostics
            return model_response_to_dict(last_result)
        return {
            "content": "(No valid model profile configured)",
            "error": "No valid model profile configured",
            "diagnostics": diagnostics,
        }

    async def chat_stream(
        self,
        messages: list[dict],
        profile_key: str = DEFAULT_MODEL,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        if messages_contain_image_payload(messages):
            yield {
                "type": "error",
                "content": (
                    "Image payloads must use gateway.describe_image_detailed so the "
                    "unified VLM image compression policy is always applied."
                ),
            }
            return
        candidate_keys = _profile_chain_for_model_type("llm", profile_key, profiles=MODEL_PROFILES)
        last_error = ""
        for idx, key in enumerate(candidate_keys):
            profile = self.get_profile(key)
            if profile["provider"] == "llama":
                try:
                    await _ensure_local_text_model(profile)
                except Exception as exc:
                    last_error = _format_exception_detail(exc)
                    if idx < len(candidate_keys) - 1:
                        logger.warning(
                            "LLM stream local profile %s failed health/startup, trying fallback %s: %s",
                            key,
                            candidate_keys[idx + 1],
                            last_error,
                        )
                        yield {
                            "type": "degradation",
                            "content": f"降级: {key} -> {candidate_keys[idx + 1]} 原因:{last_error[:300]}",
                        }
                        continue
                    yield {"type": "error", "content": f"Model stream fallback exhausted: {last_error}"}
                    return
            provider = self.get_provider(profile["provider"])
            emitted_content = False
            try:
                async for event in provider.chat_stream(
                    messages=messages,
                    model=profile["model"],
                    temperature=profile["temperature"],
                    max_tokens=profile["max_tokens"],
                    tools=tools,
                ):
                    if event.get("type") == "error":
                        last_error = str(event.get("content") or "")
                        if is_protocol_error_text(last_error) or emitted_content:
                            yield event
                            return
                        raise RuntimeError(last_error)
                    if event.get("type") in {"token", "thinking", "tool_call"}:
                        emitted_content = True
                    yield event
                if idx > 0:
                    logger.warning("LLM stream fallback succeeded: %s", key)
                return
            except Exception as exc:
                last_error = _format_exception_detail(exc)
                if is_protocol_error_text(last_error) or emitted_content:
                    yield {"type": "error", "content": last_error}
                    return
                if idx < len(candidate_keys) - 1:
                    logger.warning(
                        "LLM stream profile %s failed before first token, trying fallback %s: %s",
                        key,
                        candidate_keys[idx + 1],
                        last_error,
                    )
                    yield {
                        "type": "degradation",
                        "content": f"降级: {key} -> {candidate_keys[idx + 1]} 原因:{last_error[:300]}",
                    }
                    continue
        yield {"type": "error", "content": f"Model stream fallback exhausted: {last_error}"}

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
        result = await self.describe_image_detailed(
            image_bytes=image_bytes,
            prompt=prompt,
            profile_key=profile_key,
            mime_type=mime_type,
        )
        return str(result.get("content") or "")

    async def describe_image_detailed(
        self,
        image_bytes: bytes,
        prompt: str = "请详细描述这张图片",
        profile_key: str | None = None,
        mime_type: str = "image/jpeg",
    ) -> dict:
        """Describe an image using the configured vision model, with fallback chain.

        Returns the text description from the vision model.
        Falls back through _VISION_FALLBACK if the primary model fails.
        """
        import base64
        prepared_bytes, prepared_mime_type, image_preprocess = prepare_vision_image_for_model_from_config(
            image_bytes,
            mime_type,
        )
        if image_preprocess.get("send_blocked"):
            raise RuntimeError(
                "Vision image preprocessing could not produce a safe compressed payload; "
                "raw image send was blocked by gateway policy."
            )
        b64 = base64.b64encode(prepared_bytes).decode("ascii")
        img_data_url = f"data:{prepared_mime_type};base64,{b64}"
        messages = [
            {"role": "system", "content": "You are an image description assistant. Describe the image in Chinese in 1-3 sentences, focusing on visual content."},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": img_data_url, "detail": "high"}},
                {"type": "text", "text": prompt},
            ]},
        ]

        # Try requested/primary → fallback chain. Explicit profile requests still
        # fall back when models.json enables fallback_on_explicit_profile.
        requested_profile = profile_key if profile_key in _VISION_PROFILES else _VISION_PRIMARY
        candidate_keys = _profile_chain_for_model_type(
            "vision",
            profile_key,
            primary_key=_VISION_PRIMARY,
            fallback_chain=_VISION_FALLBACK,
            profiles=_VISION_PROFILES,
        )
        diagnostics: dict = {
            "requested_profile": requested_profile,
            "candidates": candidate_keys,
            "attempts": [],
            "fallback_used": False,
            "image_preprocess": image_preprocess,
        }
        last_error = None
        for idx, key in enumerate(candidate_keys):
            profile = _VISION_PROFILES.get(key)
            if not profile:
                continue
            try:
                if profile.get("provider") == "llama":
                    await _ensure_local_vision_model(profile)
                provider = self.get_provider(profile["provider"])
                raw = await provider.chat(
                    messages=messages,
                    model=profile.get("model", key),
                    temperature=profile.get("temperature", 0.7),
                    max_tokens=profile.get("max_tokens", 4096),
                    tools=None,
                )
                if "error" in raw:
                    raise RuntimeError(raw.get("content") or raw.get("error"))
                if profile.get("provider") in ("local",):
                    content = raw.get("content", "")
                    if content:
                        diagnostics["selected_profile"] = key
                        diagnostics["selected_provider"] = profile.get("provider", "")
                        diagnostics["fallback_used"] = idx > 0
                        diagnostics["attempts"].append({
                            "profile": key,
                            "provider": profile.get("provider", ""),
                            "model": profile.get("model", key),
                            "success": True,
                            "error": None,
                        })
                        return {"content": content, "diagnostics": diagnostics}
                adapter = get_adapter(profile.get("model", key))
                result = adapter.adapt_response(raw, provider=profile.get("provider", ""))
                content = result.content.strip()
                if content:
                    usage = _extract_usage(raw)
                    if usage:
                        await log_usage(
                            model_key=key,
                            prompt_tokens=usage.prompt_tokens,
                            completion_tokens=usage.completion_tokens,
                            provider_name=profile.get("provider", ""),
                            caller_module="gateway.describe_image",
                        )
                    diagnostics["selected_profile"] = key
                    diagnostics["selected_provider"] = profile.get("provider", "")
                    diagnostics["fallback_used"] = idx > 0
                    diagnostics["attempts"].append({
                        "profile": key,
                        "provider": profile.get("provider", ""),
                        "model": profile.get("model", key),
                        "success": True,
                        "error": None,
                    })
                    return {"content": content, "diagnostics": diagnostics}
            except Exception as exc:
                diagnostics["attempts"].append({
                    "profile": key,
                    "provider": profile.get("provider", ""),
                    "model": profile.get("model", key),
                    "success": False,
                    "error": _format_exception_detail(exc),
                })
                logger.warning("Vision model %s failed (attempt %d/%d): %s", key, idx + 1, len(candidate_keys), exc)
                last_error = exc
                continue
        raise RuntimeError(f"All vision models failed. Last error: {last_error}")

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        count: int = 1,
    ) -> dict:
        """Generate images using configured image generation provider.

        Returns dict with "images" list (each item has "b64" base64 content)
        and "placeholder" bool.
        Falls back from primary to fallback chain on failure.
        """
        img_cfg = get_model_type_config("image_gen")
        primary = img_cfg.get("primary", "")
        fallback_chain = img_cfg.get("fallback_chain", [])
        profiles = img_cfg.get("profiles", {})

        candidate_keys = [primary] + fallback_chain if primary else fallback_chain
        last_error = None

        for idx, key in enumerate(candidate_keys):
            profile = profiles.get(key)
            if not profile:
                continue
            provider_name = profile.get("provider", "")
            provider = self._providers.get(provider_name)
            if not provider:
                continue
            try:
                from app.config import get_settings
                cfg = get_settings()
                api_key = cfg.GPTSTORE_API_KEY
                base_url = cfg.GPTSTORE_BASE_URL.rstrip("/")
                proxy_url = cfg.GPTSTORE_PROXY

                if not api_key:
                    raise NotImplementedError("GPTSTORE_API_KEY not configured")

                import re
                tool_config: dict = {"type": "image_generation"}
                m = re.match(r"^(\d+)\s*[xX]\s*(\d+)$", size.strip())
                if m:
                    tool_config["dimensions"] = f"{m.group(1)}x{m.group(2)}"

                import random

                import httpx

                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        client_kw: dict = {
                            "timeout": httpx.Timeout(180.0),
                            "follow_redirects": True,
                        }
                        if proxy_url:
                            client_kw["proxy"] = httpx.Proxy(url=proxy_url)

                        async with httpx.AsyncClient(**client_kw) as client:
                            model_name = profile.get("model")
                            if not model_name:
                                raise RuntimeError(f"Image generation profile '{key}' is missing model")
                            body = {
                                "model": model_name,
                                "input": prompt,
                                "tools": [tool_config],
                                "store": False,
                            }
                            resp = await client.post(
                                f"{base_url}/responses",
                                json=body,
                                headers={"Authorization": f"Bearer {api_key}"},
                            )
                            resp.raise_for_status()
                            data = resp.json()

                            images: list[dict] = []
                            for item in data.get("output", []):
                                if item.get("type") == "image_generation_call":
                                    raw = item.get("result") or item.get("b64_json")
                                    if raw:
                                        images.append({"b64": raw, "index": len(images)})

                            if images:
                                await log_usage(
                                    model_key=key,
                                    prompt_tokens=len(prompt),
                                    completion_tokens=len(images) * 1000,
                                    provider_name=provider_name,
                                    caller_module="gateway.generate_image",
                                )
                                return {"images": images, "placeholder": False}
                            raise ValueError("No image returned (retryable)")
                    except Exception as e:
                        last_error = str(e)
                        el = str(e).lower()
                        retryable = any(kw in el for kw in [
                            "not enabled", "no available", "upstream",
                            "403", "forbidden", "429", "rate limit",
                            "no image returned", "bad gateway",
                            "500", "502", "503", "timeout", "connection",
                        ])
                        if retryable and attempt < max_retries - 1:
                            await asyncio.sleep(1.0 + random.random())
                            continue
                        elif retryable:
                            raise RuntimeError(f"Image gen exhausted: {e}")
                        else:
                            raise
            except NotImplementedError:
                raise
            except Exception as exc:
                logger.warning("Image gen provider '%s' failed: %s", key, exc)
                last_error = exc
                continue

        raise RuntimeError(f"All image gen providers failed. Last error: {last_error}")

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
    watchdog_name = (profile or {}).get("watchdog") or (profile or {}).get("model")
    if not watchdog_name:
        raise RuntimeError("Local text model profile is missing watchdog/model in models.json")
    await to_thread(ensure_model, watchdog_name)


async def _ensure_local_vision_model(profile: dict) -> None:
    """Ensure a local vision model is running via the configured watchdog."""
    from asyncio import to_thread

    from app.services.model_watchdog.watchdog import ensure_model
    watchdog_name = profile.get("watchdog") or profile.get("model")
    if not watchdog_name:
        raise RuntimeError("Local vision model profile is missing watchdog/model in models.json")
    await to_thread(ensure_model, watchdog_name)
