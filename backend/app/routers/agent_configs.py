from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.core.exceptions import NotFound, ConflictError
from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.models.system import AgentConfig

router = APIRouter(prefix="/api/agent-configs", tags=["agent-configs"])


class AgentConfigCreate(BaseModel):
    agent_code: str
    agent_name: str = ""
    provider: str = ""
    model: str = ""
    system_prompt: str = ""
    purpose: str = ""
    enabled: bool = True
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    timeout_ms: int | None = None
    fallback_model: str | None = None
    fallback_enabled: bool = False
    max_concurrency: int | None = None
    cooldown_seconds: int | None = None
    retry_count: int = 3
    daily_call_limit: int | None = None
    daily_budget: float | None = None
    monthly_budget: float | None = None
    response_format: str = "text"
    log_prompt_enabled: bool = True
    log_response_enabled: bool = True
    sensitive_action_policy: str = "confirm"


class AgentConfigUpdate(BaseModel):
    agent_name: str | None = None
    provider: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    purpose: str | None = None
    enabled: bool | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    timeout_ms: int | None = None
    fallback_model: str | None = None
    fallback_enabled: bool | None = None
    max_concurrency: int | None = None
    cooldown_seconds: int | None = None
    retry_count: int | None = None
    daily_call_limit: int | None = None
    daily_budget: float | None = None
    monthly_budget: float | None = None
    response_format: str | None = None
    log_prompt_enabled: bool | None = None
    log_response_enabled: bool | None = None
    sensitive_action_policy: str | None = None


def _config_to_dict(c: AgentConfig) -> dict:
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


@router.get("/")
async def list_agent_configs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    r = await db.execute(
        select(AgentConfig).order_by(AgentConfig.agent_code)
    )
    configs = r.scalars().all()
    return ApiResponse(data=[_config_to_dict(c) for c in configs])


@router.get("/{agent_code}")
async def get_agent_config(
    agent_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    r = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_code == agent_code)
    )
    c = r.scalar_one_or_none()
    if not c:
        raise NotFound(f"Agent config '{agent_code}' not found")
    return ApiResponse(data=_config_to_dict(c))


@router.post("/")
async def create_agent_config(
    body: AgentConfigCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    r = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_code == body.agent_code)
    )
    if r.scalar_one_or_none():
        raise ConflictError(f"Agent config '{body.agent_code}' already exists")
    config = AgentConfig(
        agent_code=body.agent_code,
        agent_name=body.agent_name,
        provider=body.provider,
        model=body.model,
        system_prompt=body.system_prompt,
        purpose=body.purpose,
        enabled=body.enabled,
        temperature=body.temperature,
        top_p=body.top_p,
        max_tokens=body.max_tokens,
        timeout_ms=body.timeout_ms,
        fallback_model=body.fallback_model,
        fallback_enabled=body.fallback_enabled,
        max_concurrency=body.max_concurrency,
        cooldown_seconds=body.cooldown_seconds,
        retry_count=body.retry_count,
        daily_call_limit=body.daily_call_limit,
        daily_budget=body.daily_budget,
        monthly_budget=body.monthly_budget,
        response_format=body.response_format,
        log_prompt_enabled=body.log_prompt_enabled,
        log_response_enabled=body.log_response_enabled,
        sensitive_action_policy=body.sensitive_action_policy,
        updated_by=user.id,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return ApiResponse(data=_config_to_dict(config))


@router.put("/{agent_code}")
async def update_agent_config(
    agent_code: str,
    body: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    r = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_code == agent_code)
    )
    config = r.scalar_one_or_none()
    if not config:
        raise NotFound(f"Agent config '{agent_code}' not found")
    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(config, field, value)
    config.updated_by = user.id
    await db.commit()
    await db.refresh(config)
    return ApiResponse(data=_config_to_dict(config))


@router.delete("/{agent_code}")
async def delete_agent_config(
    agent_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    r = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_code == agent_code)
    )
    config = r.scalar_one_or_none()
    if not config:
        raise NotFound(f"Agent config '{agent_code}' not found")
    await db.delete(config)
    await db.commit()
    return ApiResponse(data={"ok": True})
