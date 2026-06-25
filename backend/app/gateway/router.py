import asyncio
import logging
import uuid
from typing import AsyncGenerator
from datetime import datetime, timezone
from .base import BaseProvider
from .opencode_provider import OpenCodeProvider
from .openai_provider import OpenAIProvider
from .local import LocalProvider
from .adapters import get_adapter
from .config import (
    DEFAULT_MODEL, _config, MODEL_PROFILES, resolve_api_key,
    TEMPLATES, ROUTING_POLICIES, DEFAULT_ROUTING_POLICY,
    BUDGET_RATES, VariantTemplate,
    resolve_template_for_role, list_templates, list_routing_policies,
)

logger = logging.getLogger("v2.gateway.router")
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0
RETRYABLE_STATUSES = {429, 502, 503, 504}

# ── Unified retry budget / attempt trace ──────────────────────────────


class RetryBudget:
    """Lightweight budget tracker shared across retry layers.

    Records every attempt so _call_with_retry, chat_with_fallback, and
    chat_with_degradation_chain can all see how many tries have been made.

    Diagnostics contract (shared with fallback chain):
      - trace_id        : propagated from caller
      - fallback_reason : when a fallback switch occurs, records the reason
      - attempt history : per-attempt profile/provider/status/reason
    """

    def __init__(self, max_retries: int = 6):
        self.max_retries = max_retries
        self.attempts: list[dict] = []
        self.trace_id: str = str(uuid.uuid4())
        self.fallback_reason: str | None = None

    def record_attempt(self, profile_key: str, provider: str, status: int | None, reason: str = "") -> None:
        self.attempts.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "profile_key": profile_key,
            "provider": provider,
            "status": status,
            "reason": _extract_reason_from_str(reason)[:200],
        })

    def record_fallback(self, from_profile: str, to_profile: str, reason: str) -> None:
        self.fallback_reason = f"{from_profile} -> {to_profile}: {_extract_reason_from_str(reason)[:200]}"
        self.attempts.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "profile_key": f"{from_profile}->{to_profile}",
            "provider": "fallback",
            "status": None,
            "reason": self.fallback_reason,
        })

    @property
    def exhausted(self) -> bool:
        return len(self.attempts) >= self.max_retries

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "max_retries": self.max_retries,
            "total_attempts": len(self.attempts),
            "fallback_reason": self.fallback_reason,
            "attempts": self.attempts,
        }

# ── Model governance ─ ModelRouter (template + routing policy + budget/health diag) ──


class ModelRouter:
    """Governance-level model router: resolves templates, evaluates policy, reports diagnostics.

    This is the control-plane layer above the existing ``ModelGatewayRouter``.
    Consumers can ask "what template should role X use?" without knowing
    about raw profile keys.
    """

    @staticmethod
    def resolve_template(role: str = "default",
                          high_ambiguity: bool = False,
                          high_cost: bool = False,
                          budget_tight: bool = False,
                          policy_name: str = "default_policy") -> VariantTemplate:
        return resolve_template_for_role(role, high_ambiguity, high_cost, budget_tight, policy_name)

    @staticmethod
    def resolve_profile_key(role: str = "default",
                             high_ambiguity: bool = False,
                             high_cost: bool = False,
                             budget_tight: bool = False,
                             policy_name: str = "default_policy") -> str:
        tpl = resolve_template_for_role(role, high_ambiguity, high_cost, budget_tight, policy_name)
        return tpl.primary_profile

    @staticmethod
    def get_template(name: str) -> VariantTemplate | None:
        return TEMPLATES.get(name)

    @staticmethod
    def list_templates() -> list[dict]:
        return list_templates()

    @staticmethod
    def list_policies() -> list[dict]:
        return list_routing_policies()

    @staticmethod
    def get_diagnostics() -> dict:
        """Return current routing state for admin observability."""
        return {
            "templates": list_templates(),
            "policies": list_routing_policies(),
            "budget_rates": {k: v for k, v in BUDGET_RATES.items()},
            "default_policy": DEFAULT_ROUTING_POLICY.name,
            "available_profiles": list(MODEL_PROFILES.keys()),
        }


# ── Cost logging helper ───────────────────────────────────────────────


async def _log_model_usage(
    model_key: str,
    prompt_tokens: int,
    completion_tokens: int,
    provider_name: str = "",
    caller_module: str = "gateway",
) -> None:
    """Log model usage costs to agent_usage_daily.

    Non-fatal: failures only logged, never raised.
    """
    try:
        profile = MODEL_PROFILES.get(model_key)
        if not profile:
            return
        price_input = profile.get("price_input") or 0
        price_output = profile.get("price_output") or 0
        if not price_input and not price_output:
            return
        cost = (prompt_tokens * price_input + completion_tokens * price_output) / 1_000_000

        from datetime import date
        from app.database import AsyncSessionLocal
        from sqlalchemy import text

        today = date.today()
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO agent_usage_daily
                (usage_date, model_key, provider, module, call_count, prompt_tokens, completion_tokens, cost)
                VALUES (:date, :model, :provider, :module, 1, :prompt_tokens, :completion_tokens, :cost)
                ON CONFLICT (usage_date, model_key, provider, module)
                DO UPDATE SET
                    call_count = agent_usage_daily.call_count + 1,
                    prompt_tokens = agent_usage_daily.prompt_tokens + :prompt_tokens,
                    completion_tokens = agent_usage_daily.completion_tokens + :completion_tokens,
                    cost = agent_usage_daily.cost + :cost
            """), {
                "date": today,
                "model": model_key,
                "provider": provider_name,
                "module": caller_module,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost": cost,
            })
            await db.commit()
    except Exception as e:
        logger.warning("Usage logging failed (non-fatal): %s", e)

# ── Vision profile loading ─────────────────────────────────────────────
_vision_cfg = _config.get("model_types", {}).get("vision", {})
_VISION_PRIMARY: str = _vision_cfg.get("primary", "mimo")
_VISION_FALLBACK: list[str] = _vision_cfg.get("fallback_chain", ["qwen3-vl"])
_VISION_PROFILES: dict[str, dict] = _vision_cfg.get("profiles", {})


def _status_code_from_exception(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    return status if isinstance(status, int) else None


def _extract_reason_from_str(reason: str) -> str:
    """Strip noisy prefixes and truncate for diagnostics."""
    return reason[:300]


def _extract_reason(exc: Exception) -> str:
    """Unified reason extraction — combines _status_code + response body truncation.

    This is the shared function that replaces the separate _extract_reason
    in fallback_chain.py and the inline error handling in gateway/router.py.
    """
    detail = str(exc)
    status = _status_code_from_exception(exc)
    if status:
        detail = f"[HTTP {status}] {detail}"
    if hasattr(exc, "response"):
        try:
            body = exc.response.text
            if body:
                detail = f"{detail[:200]} | body:{body[:500]}"
        except Exception:
            pass
    return detail[:500]


def _is_retryable_exception(exc: Exception) -> bool:
    status_code = _status_code_from_exception(exc)
    if status_code in RETRYABLE_STATUSES:
        return True
    return isinstance(exc, (ConnectionError, TimeoutError, asyncio.TimeoutError))


def list_model_profiles() -> list[dict]:
    """Return public LLM profile metadata for routers and modules."""
    return [
        {"key": key, "name": key, "provider": profile["provider"], "model": profile["model"]}
        for key, profile in MODEL_PROFILES.items()
    ]


async def _call_with_retry(
    provider: BaseProvider,
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    tools: list[dict] | None,
    budget: RetryBudget | None = None,
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
            status = _status_code_from_exception(exc)
            if budget:
                budget.record_attempt(
                    profile_key=model,
                    provider=getattr(provider, "name", type(provider).__name__),
                    status=status,
                    reason=str(exc),
                )
            if not _is_retryable_exception(exc) or attempt_index == RETRY_MAX_ATTEMPTS - 1:
                raise
            delay = RETRY_BASE_DELAY_SECONDS * (2 ** attempt_index)
            logger.warning(
                "AI gateway call attempt %d/%d failed (status=%s), retrying in %.1fs, budget_used=%d",
                attempt_index + 1,
                RETRY_MAX_ATTEMPTS,
                status,
                delay,
                len(budget.attempts) if budget else 0,
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
                    api_key=resolve_api_key(cfg),
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
        return list_model_profiles()

    def resolve_template(self, role: str = "default",
                          high_ambiguity: bool = False,
                          high_cost: bool = False,
                          budget_tight: bool = False,
                          policy_name: str = "default_policy") -> VariantTemplate:
        return resolve_template_for_role(role, high_ambiguity, high_cost, budget_tight, policy_name)

    def resolve_profile_key_for_role(self, role: str = "default",
                                      high_ambiguity: bool = False,
                                      high_cost: bool = False,
                                      budget_tight: bool = False,
                                      policy_name: str = "default_policy") -> str:
        tpl = resolve_template_for_role(role, high_ambiguity, high_cost, budget_tight, policy_name)
        return tpl.primary_profile

    def get_routing_diagnostics(self) -> dict:
        return ModelRouter.get_diagnostics()

    def get_failover_diagnostics(self) -> dict:
        """Return failover / fallback / health diagnostic state."""
        profiles = []
        for key, profile in MODEL_PROFILES.items():
            profiles.append({
                "key": key,
                "provider": profile.get("provider", ""),
                "model": profile.get("model", ""),
            })
        return {
            "profiles": profiles,
            "profiles_available": len(MODEL_PROFILES),
            "providers_configured": list(self._providers.keys()) if hasattr(self, '_providers') else [],
        }

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
        budget = budget or RetryBudget()
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
                budget=budget,
            )
        except Exception as exc:
            detail = str(exc)
            if hasattr(exc, "response"):
                try:
                    body = exc.response.text
                    if body:
                        detail = f"{detail}\n响应体: {body[:1000]}"
                except Exception:
                    pass
            logger.error("AI gateway chat failed: %s", detail)
            return {"error": str(exc), "content": f"(Model error: {detail})", "_retry_budget": budget.to_dict()}
        if "error" in raw:
            raw["_retry_budget"] = budget.to_dict()
            return raw
        # Log usage cost
        if "usage" in raw:
            pt = raw["usage"].get("prompt_tokens", 0) or 0
            ct = raw["usage"].get("completion_tokens", 0) or 0
            if pt > 0 or ct > 0:
                await _log_model_usage(
                    model_key=profile_key,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    provider_name=profile.get("provider", ""),
                    caller_module="gateway.chat",
                )
        result = raw if profile["provider"] in ("local",) else get_adapter(profile["model"]).adapt_response(raw, provider=profile["provider"])
        result["_retry_budget"] = budget.to_dict()
        return result

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
                    content = raw.get("content", "")
                    if content:
                        return content
                adapter = get_adapter(profile.get("model", key))
                result = adapter.adapt_response(raw, provider=profile.get("provider", ""))
                content = (result.get("content") or "").strip()
                if content:
                    # Log vision model usage cost
                    if "usage" in raw:
                        pt = raw["usage"].get("prompt_tokens", 0) or 0
                        ct = raw["usage"].get("completion_tokens", 0) or 0
                        if pt > 0 or ct > 0:
                            await _log_model_usage(
                                model_key=key,
                                prompt_tokens=pt,
                                completion_tokens=ct,
                                provider_name=profile.get("provider", ""),
                                caller_module="gateway.describe_image",
                            )
                    return content
            except Exception as exc:
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
        img_cfg = _config.get("model_types", {}).get("image_gen", {})
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

                import httpx
                import base64 as b64
                import random

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
                            body = {
                                "model": profile.get("model", "gpt-5.5"),
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
                                # Log usage (estimate tokens based on image count)
                                await _log_model_usage(
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
