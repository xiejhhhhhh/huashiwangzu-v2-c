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

DEFAULT_MODEL = "deepseek-v4-flash"

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
