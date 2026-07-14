"""Gateway configuration backed by ``data/config/models.json``.

This module is the single source of truth for model routing, role-based
templates, and budget policy data consumed by both ``gateway.router`` and
``gateway.service``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("v2.gateway.config")

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
    with open(_MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
        _CONFIG = json.load(f)
    return _CONFIG


_config = _load_models_config()
MODEL_PROFILES: dict[str, dict] = _config.get("model_types", {}).get("llm", {}).get("profiles", {})
DEFAULT_MODEL = str(
    _config.get("model_types", {}).get("llm", {}).get("primary")
    or next(iter(MODEL_PROFILES), "")
)


def get_models_config() -> dict:
    """Return the cached raw models.json config."""
    return _load_models_config()


def get_models_config_path() -> Path:
    return _MODELS_CONFIG_PATH


def get_provider_configs() -> dict[str, dict]:
    return get_models_config().get("providers", {})


def get_model_type_config(model_type: str) -> dict:
    return get_models_config().get("model_types", {}).get(model_type, {})


def get_profiles_for_type(model_type: str) -> dict[str, dict]:
    return get_model_type_config(model_type).get("profiles", {})


def get_model_profiles() -> dict[str, dict]:
    return MODEL_PROFILES


def get_fallback_chain(model_type: str = "llm") -> list[str]:
    return list(get_model_type_config(model_type).get("fallback_chain", []))


def get_watchdog_model_configs() -> dict[str, dict]:
    return get_models_config().get("watchdog_models", {})


def resolve_api_key(provider_cfg: dict) -> str:
    env_name = provider_cfg.get("api_key_env", "")
    if not env_name:
        return ""
    from app.config import get_settings
    key = getattr(get_settings(), env_name, "")
    if not key:
        logger.warning("Provider config references %s but it is empty in settings", env_name)
    return key


@dataclass(frozen=True)
class VariantTemplate:
    name: str
    primary_profile: str
    description: str = ""


DEFAULT_ROUTING_POLICY = VariantTemplate(name="default_policy", primary_profile=DEFAULT_MODEL)
ROUTING_POLICIES: dict[str, VariantTemplate] = {
    DEFAULT_ROUTING_POLICY.name: DEFAULT_ROUTING_POLICY,
}
TEMPLATES: dict[str, VariantTemplate] = {
    "default": DEFAULT_ROUTING_POLICY,
}
BUDGET_RATES: dict[str, float] = {
    "default": 1.0,
}


def resolve_template_for_role(
    role: str = "default",
    high_ambiguity: bool = False,
    high_cost: bool = False,
    budget_tight: bool = False,
    policy_name: str = "default_policy",
) -> VariantTemplate:
    return TEMPLATES.get(role) or TEMPLATES["default"]


def list_templates() -> list[dict]:
    return [
        {"name": tpl.name, "primary_profile": tpl.primary_profile, "description": tpl.description}
        for tpl in TEMPLATES.values()
    ]


def list_routing_policies() -> list[dict]:
    return [
        {"name": policy.name, "primary_profile": policy.primary_profile, "description": policy.description}
        for policy in ROUTING_POLICIES.values()
    ]


def reload_config() -> dict:
    """热重载 models.json 配置，清除缓存并刷新全局变量。

    供 model-router 管理模块在写完配置文件后调用，避免重启后端进程。
    注意：``gateway_router`` (ModelGatewayRouter 单例) 内部的 provider 实例
    是在 __init__ 时基于 providers 配置构建的，改 provider 配置后仍需调用方
    自行重建 provider 缓存（见 app.gateway.router.gateway_router._providers）。
    """
    global _CONFIG, MODEL_PROFILES, DEFAULT_MODEL
    _CONFIG = None
    config = _load_models_config()
    MODEL_PROFILES = config.get("model_types", {}).get("llm", {}).get("profiles", {})
    DEFAULT_MODEL = str(
        config.get("model_types", {}).get("llm", {}).get("primary")
        or next(iter(MODEL_PROFILES), "")
    )
    return {"status": "reloaded", "profiles": list(MODEL_PROFILES.keys()), "default": DEFAULT_MODEL}
