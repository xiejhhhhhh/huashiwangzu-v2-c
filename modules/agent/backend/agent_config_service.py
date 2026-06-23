"""Agent config CRUD service layer.

Extracted from router.py to follow Router → Service → Model layering.
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AgentConfig
from app.core.exceptions import NotFound

logger = logging.getLogger("v2.agent").getChild("config_service")


def _config_to_dict(c) -> dict:
    return {
        "id": c.id,
        "agent_code": c.agent_code,
        "agent_name": c.agent_name,
        "provider": c.provider,
        "model": c.model,
        "system_prompt": c.system_prompt,
        "purpose": c.purpose,
        "enabled": c.enabled,
        "temperature": c.temperature,
        "top_p": c.top_p,
        "max_tokens": c.max_tokens,
        "timeout_ms": c.timeout_ms,
        "fallback_model": c.fallback_model,
        "fallback_enabled": c.fallback_enabled,
        "max_concurrency": c.max_concurrency,
        "cooldown_seconds": c.cooldown_seconds,
        "retry_count": c.retry_count,
        "daily_call_limit": c.daily_call_limit,
        "daily_budget": c.daily_budget,
        "monthly_budget": c.monthly_budget,
        "response_format": c.response_format,
        "log_prompt_enabled": c.log_prompt_enabled,
        "log_response_enabled": c.log_response_enabled,
        "sensitive_action_policy": c.sensitive_action_policy,
        "updated_by": c.updated_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


async def list_configs(db: AsyncSession) -> list[dict]:
    r = await db.execute(select(AgentConfig).order_by(AgentConfig.agent_code))
    return [_config_to_dict(c) for c in r.scalars().all()]


async def get_config(db: AsyncSession, agent_code: str) -> dict:
    r = await db.execute(select(AgentConfig).where(AgentConfig.agent_code == agent_code))
    c = r.scalar_one_or_none()
    if not c:
        raise NotFound(f"Agent config '{agent_code}' not found")
    return _config_to_dict(c)


async def create_config(db: AsyncSession, data: dict, user_id: int) -> dict:
    exists = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_code == data["agent_code"])
    )
    if exists.scalar_one_or_none():
        from app.core.exceptions import ConflictError
        raise ConflictError(f"Agent config '{data['agent_code']}' already exists")
    config = AgentConfig(
        agent_code=data["agent_code"], agent_name=data.get("agent_name", ""),
        provider=data.get("provider", ""), model=data.get("model", ""),
        system_prompt=data.get("system_prompt", ""), purpose=data.get("purpose", ""),
        enabled=data.get("enabled", True),
        temperature=data.get("temperature"), top_p=data.get("top_p"),
        max_tokens=data.get("max_tokens"), timeout_ms=data.get("timeout_ms"),
        fallback_model=data.get("fallback_model"),
        fallback_enabled=data.get("fallback_enabled", True),
        max_concurrency=data.get("max_concurrency"),
        cooldown_seconds=data.get("cooldown_seconds"),
        retry_count=data.get("retry_count"),
        daily_call_limit=data.get("daily_call_limit"),
        daily_budget=data.get("daily_budget"),
        monthly_budget=data.get("monthly_budget"),
        response_format=data.get("response_format"),
        log_prompt_enabled=data.get("log_prompt_enabled", True),
        log_response_enabled=data.get("log_response_enabled", True),
        sensitive_action_policy=data.get("sensitive_action_policy", "log"),
        updated_by=user_id,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return _config_to_dict(config)


async def update_config(db: AsyncSession, agent_code: str, updates: dict, user_id: int) -> dict:
    r = await db.execute(select(AgentConfig).where(AgentConfig.agent_code == agent_code))
    config = r.scalar_one_or_none()
    if not config:
        raise NotFound(f"Agent config '{agent_code}' not found")
    for field, value in updates.items():
        setattr(config, field, value)
    config.updated_by = user_id
    await db.commit()
    await db.refresh(config)
    return _config_to_dict(config)


async def delete_config(db: AsyncSession, agent_code: str) -> dict:
    r = await db.execute(select(AgentConfig).where(AgentConfig.agent_code == agent_code))
    config = r.scalar_one_or_none()
    if not config:
        raise NotFound(f"Agent config '{agent_code}' not found")
    await db.delete(config)
    await db.commit()
    return {"ok": True}
