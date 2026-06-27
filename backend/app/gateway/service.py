"""Gateway service layer — stable public API for model gateway operations.

Consumers should import from here instead of touching gateway router
implementation details or its internal config globals directly.

v2 model governance: exposes role-based template routing, budget/health
diagnostics, and policy evaluation.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from .base import BaseProvider
from .config import (
    BUDGET_RATES,
    DEFAULT_MODEL,
    DEFAULT_ROUTING_POLICY,
    MODEL_PROFILES,
    TEMPLATES,
    VariantTemplate,
    _config,
    list_routing_policies,
    list_templates,
    resolve_api_key,
    resolve_template_for_role,
)
from .local import LocalProvider
from .openai_provider import OpenAIProvider
from .opencode_provider import OpenCodeProvider
from .router import ModelGatewayRouter, RetryBudget

logger = logging.getLogger("v2.gateway.service")

_GATEWAY_ROUTER = ModelGatewayRouter()


def list_model_profiles() -> list[dict]:
    return [
        {"key": key, "name": key, "provider": profile["provider"], "model": profile["model"]}
        for key, profile in MODEL_PROFILES.items()
    ]


def get_model_profile(profile_key: str) -> dict:
    profile = MODEL_PROFILES.get(profile_key) or MODEL_PROFILES.get(DEFAULT_MODEL)
    if not profile:
        raise RuntimeError("No LLM model profiles configured in models.json")
    return profile


def get_model_profile_safe(profile_key: str) -> dict | None:
    return MODEL_PROFILES.get(profile_key)


def get_model_provider(provider_name: str) -> BaseProvider:
    providers_config = _config.get("providers", {})
    cfg = providers_config.get(provider_name)
    if not cfg:
        if providers_config.get("local"):
            return LocalProvider()
        raise RuntimeError(f"Model provider '{provider_name}' is not configured")
    ptype = cfg.get("type", "")
    if ptype == "opencode":
        return OpenCodeProvider(api_url=cfg.get("api_url", ""))
    if ptype == "openai_compat":
        api_key = resolve_api_key(cfg)
        return OpenAIProvider(
            api_url=cfg.get("api_url", ""),
            api_key=api_key,
            provider_name=cfg.get("provider_name", provider_name),
        )
    if ptype == "local":
        return LocalProvider()
    if providers_config.get("local"):
        return LocalProvider()
    raise RuntimeError(f"Model provider '{provider_name}' is not configured")


def get_fallback_chain() -> list[str]:
    return _config.get("model_types", {}).get("llm", {}).get("fallback_chain", [])


def get_default_model() -> str:
    return DEFAULT_MODEL


def resolve_role_profile(role: str = "default",
                          high_ambiguity: bool = False,
                          high_cost: bool = False,
                          budget_tight: bool = False,
                          policy_name: str = "default_policy") -> str:
    """Resolve a profile key for the given agent role and context.

    Returns the primary_profile from the resolved variant template.
    """
    template = resolve_template_for_role(role, high_ambiguity, high_cost, budget_tight, policy_name)
    return template.primary_profile


def resolve_role_template(role: str = "default",
                           high_ambiguity: bool = False,
                           high_cost: bool = False,
                           budget_tight: bool = False,
                           policy_name: str = "default_policy") -> VariantTemplate:
    """Resolve the full VariantTemplate for a given role and context."""
    return resolve_template_for_role(role, high_ambiguity, high_cost, budget_tight, policy_name)


async def chat(
    messages: list[dict],
    profile_key: str = DEFAULT_MODEL,
    tools: list[dict] | None = None,
    budget: RetryBudget | None = None,
) -> dict:
    return await _GATEWAY_ROUTER.chat(messages=messages, profile_key=profile_key, tools=tools, budget=budget)


async def chat_with_role(
    messages: list[dict],
    role: str = "default",
    tools: list[dict] | None = None,
    budget: RetryBudget | None = None,
    high_ambiguity: bool = False,
    high_cost: bool = False,
    budget_tight: bool = False,
) -> dict:
    """Chat using role-based template routing instead of a raw profile_key."""
    template = resolve_role_template(role, high_ambiguity, high_cost, budget_tight)
    return await _GATEWAY_ROUTER.chat(
        messages=messages,
        profile_key=template.primary_profile,
        tools=tools,
        budget=budget,
    )


async def chat_with_template(
    messages: list[dict],
    template_name: str = "default",
    tools: list[dict] | None = None,
    budget: RetryBudget | None = None,
) -> dict:
    """Chat using a named template directly."""
    template = TEMPLATES.get(template_name)
    if not template:
        template = resolve_role_template("default")
    return await _GATEWAY_ROUTER.chat(
        messages=messages,
        profile_key=template.primary_profile,
        tools=tools,
        budget=budget,
    )


async def chat_stream(
    messages: list[dict],
    profile_key: str = DEFAULT_MODEL,
    tools: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    async for event in _GATEWAY_ROUTER.chat_stream(messages=messages, profile_key=profile_key, tools=tools):
        yield event


async def chat_stream_with_role(
    messages: list[dict],
    role: str = "default",
    tools: list[dict] | None = None,
    high_ambiguity: bool = False,
    high_cost: bool = False,
    budget_tight: bool = False,
) -> AsyncGenerator[dict, None]:
    """Streaming chat using role-based template routing."""
    template = resolve_role_template(role, high_ambiguity, high_cost, budget_tight)
    async for event in _GATEWAY_ROUTER.chat_stream(
        messages=messages,
        profile_key=template.primary_profile,
        tools=tools,
    ):
        yield event


def get_routing_diagnostics() -> dict:
    """Return current routing governance state for admin / observability."""
    return {
        "templates": list_templates(),
        "policies": list_routing_policies(),
        "budget_rates": {k: v for k, v in BUDGET_RATES.items()},
        "default_policy": DEFAULT_ROUTING_POLICY.name,
    }
