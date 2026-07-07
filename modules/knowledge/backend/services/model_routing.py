"""Model routing helpers for knowledge-module model stages."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

from app.gateway.config import get_model_type_config, get_models_config, get_models_config_path

logger = logging.getLogger("v2.knowledge").getChild("model_routing")

KNOWLEDGE_ROUTING_KEY = "knowledge"
DEFAULT_MODEL_CALL_GLOBAL_CONCURRENCY = 10

_model_call_active = 0
_model_call_condition: asyncio.Condition | None = None
_model_call_condition_loop: asyncio.AbstractEventLoop | None = None


def _knowledge_routing_config() -> dict[str, Any]:
    config = _fresh_models_config().get("module_routing", {})
    routing = config.get(KNOWLEDGE_ROUTING_KEY, {}) if isinstance(config, dict) else {}
    return routing if isinstance(routing, dict) else {}


def _fresh_models_config() -> dict[str, Any]:
    """Read models.json at stage start so runtime knobs can change between batches."""
    path = get_models_config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as exc:
        logger.warning("Cannot reload models.json from %s; using cached config: %s", path, exc)
        return get_models_config()
    return config if isinstance(config, dict) else get_models_config()


def _known_llm_profiles() -> dict[str, Any]:
    profiles = _fresh_models_config().get("model_types", {}).get("llm", {}).get("profiles", {})
    return profiles if isinstance(profiles, dict) else {}


def _known_vision_profiles() -> dict[str, Any]:
    profiles = _fresh_models_config().get("model_types", {}).get("vision", {}).get("profiles", {})
    return profiles if isinstance(profiles, dict) else {}


def _primary_profile(model_type: str) -> str | None:
    model_cfg = _fresh_models_config().get("model_types", {}).get(model_type, {})
    if not isinstance(model_cfg, dict):
        return None
    primary = model_cfg.get("primary")
    return str(primary) if primary else None


def _configured_stage_profile(stage: str, *, model_type: str) -> str | None:
    routing = _knowledge_routing_config()
    stages = routing.get("stages", {}) if isinstance(routing.get("stages"), dict) else {}
    default_key = "default_vision_profile" if model_type == "vision" else "default_profile"
    configured = stages.get(stage) or routing.get(default_key) or _primary_profile(model_type)
    return str(configured) if configured else None


def _resolve_configured_profile(
    *,
    stage: str,
    model_type: str,
    profiles: dict[str, Any],
) -> str:
    profile = _configured_stage_profile(stage, model_type=model_type)
    if profile and profile in profiles:
        return profile

    primary = _primary_profile(model_type)
    if primary and primary in profiles:
        if profile and profile != primary:
            logger.warning(
                "Knowledge %s profile '%s' for stage=%s is not configured; using configured primary %s",
                model_type,
                profile,
                stage,
                primary,
            )
        return primary

    raise RuntimeError(
        f"Knowledge {model_type} routing for stage={stage} is missing a valid profile in models.json"
    )


def resolve_knowledge_profile(stage: str, override: str | None = None) -> str:
    """Resolve the model profile for a knowledge LLM stage from models.json."""
    if override:
        return override

    return _resolve_configured_profile(
        stage=stage,
        model_type="llm",
        profiles=_known_llm_profiles(),
    )


def resolve_knowledge_vision_profile(stage: str, override: str | None = None) -> str:
    """Resolve the model profile for a knowledge VLM stage from models.json."""
    if override:
        return override

    return _resolve_configured_profile(
        stage=stage,
        model_type="vision",
        profiles=_known_vision_profiles(),
    )


def pause_after_model_fallback() -> bool:
    """Whether a knowledge pipeline should pause after an LLM profile fallback."""
    routing = _knowledge_routing_config()
    return bool(routing.get("pause_after_fallback", True))


def should_pause_after_result(result: dict[str, Any]) -> bool:
    """Return True when a stage result should stop later deep stages."""
    if not pause_after_model_fallback():
        return False
    return bool(result.get("model_degraded"))


def resolve_knowledge_concurrency(
    stage: str,
    default: int,
    *,
    minimum: int = 1,
    maximum: int = 32,
) -> int:
    """Resolve a bounded per-stage knowledge concurrency knob from models.json."""
    routing = _knowledge_routing_config()
    raw_config = routing.get("pipeline_concurrency") or routing.get("concurrency") or {}
    config = raw_config if isinstance(raw_config, dict) else {}
    raw_value = config.get(stage)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        logger.warning("Invalid knowledge concurrency for stage=%s: %r", stage, raw_value)
        return default
    return max(minimum, min(maximum, value))


def resolve_knowledge_pipeline_priority(stage: str, default: int) -> int:
    """Resolve a per-stage queue priority knob from models.json."""
    routing = _knowledge_routing_config()
    raw_config = routing.get("pipeline_priorities") or routing.get("priorities") or {}
    config = raw_config if isinstance(raw_config, dict) else {}
    raw_value = config.get(stage)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        logger.warning("Invalid knowledge queue priority for stage=%s: %r", stage, raw_value)
        return default
    return max(0, min(100, value))


def resolve_knowledge_image_preprocess_int(
    key: str,
    default: int,
    *,
    minimum: int = 1,
    maximum: int = 100_000_000,
) -> int:
    """Resolve an image preprocessing integer knob from models.json."""
    routing = _knowledge_routing_config()
    raw_config = routing.get("image_preprocess") or {}
    config = raw_config if isinstance(raw_config, dict) else {}
    raw_value = config.get(key)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        logger.warning("Invalid knowledge image preprocess config %s=%r", key, raw_value)
        return default
    return max(minimum, min(maximum, value))


def resolve_knowledge_model_call_concurrency(default: int = DEFAULT_MODEL_CALL_GLOBAL_CONCURRENCY) -> int:
    """Resolve the global in-process LLM/VLM call cap for the knowledge worker."""
    return resolve_knowledge_concurrency(
        "model_call_global",
        default,
        minimum=1,
        maximum=64,
    )


def knowledge_model_call_active_count() -> int:
    """Return current in-process knowledge model calls, for diagnostics/tests."""
    return _model_call_active


def _model_call_condition_for_loop() -> asyncio.Condition:
    global _model_call_condition, _model_call_condition_loop
    loop = asyncio.get_running_loop()
    if _model_call_condition is None or _model_call_condition_loop is not loop:
        _model_call_condition = asyncio.Condition()
        _model_call_condition_loop = loop
    return _model_call_condition


@asynccontextmanager
async def knowledge_model_call_slot(stage: str):
    """Hot-configurable global model-call limiter for knowledge LLM/VLM requests.

    File-level worker lanes stay separate. This gate caps the expensive external
    model requests across raw/fusion/profile/graph work inside the active worker
    process, so stage-level page concurrency can be raised without flooding the
    relay. Reducing the JSON value makes new calls wait until active calls drain.
    """
    global _model_call_active
    wait_started = perf_counter()
    limit = resolve_knowledge_model_call_concurrency()
    condition = _model_call_condition_for_loop()
    async with condition:
        while _model_call_active >= limit:
            await condition.wait()
            limit = resolve_knowledge_model_call_concurrency()
        _model_call_active += 1
        active = _model_call_active
    wait_ms = round((perf_counter() - wait_started) * 1000)
    try:
        if wait_ms > 1000:
            logger.info(
                "Knowledge model call waited stage=%s wait_ms=%d active=%d limit=%d",
                stage,
                wait_ms,
                active,
                limit,
            )
        yield {
            "limit": limit,
            "wait_ms": wait_ms,
            "active_at_acquire": active,
        }
    finally:
        async with condition:
            _model_call_active = max(0, _model_call_active - 1)
            condition.notify_all()
