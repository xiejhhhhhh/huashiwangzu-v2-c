import json
import logging
from datetime import datetime

logger = logging.getLogger("v2.agent").getChild("router")

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.gateway.router import gateway_router
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse

from .init_db import ensure_default_prompts, ensure_timeline_column, ensure_user_profile, update_existing_prompts, ensure_event_table, ensure_processing_column, run_init
from . import tool_discovery

router = APIRouter(prefix="/api/agent", tags=["agent"])

# 注册后台任务处理器（框架 worker 自动消费）
from .handlers import tasks  # noqa: F401 — triggers register_task_handler calls


def _j(obj) -> str:
    """json.dumps with datetime fallback."""
    return json.dumps(obj, ensure_ascii=False, default=str)


def _conversation_payload(item) -> dict:
    return {"id": item.id, "title": item.title, "status": item.status}


# ── Request Schemas ──

class CreateConvRequest(BaseModel):
    title: str = "新对话"


class RenameConvRequest(BaseModel):
    title: str


class ChatRequest(BaseModel):
    conversation_id: int
    content: str
    profile_key: str | None = None


class UpdatePromptRequest(BaseModel):
    content: str


class ApprovalDecision(BaseModel):
    decision: str  # "approved" | "rejected"
    reason: str | None = None


# ── Health / Profiles / Tools ──

@router.get("/health")
async def health():
    return ApiResponse(data={"module": "agent", "status": "ok"})


@router.get("/profiles")
async def list_profiles(user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=gateway_router.list_profiles())


@router.get("/tools")
async def list_tools(user: User = Depends(require_permission("viewer"))):
    tools = tool_discovery.build_tools(user.role)
    return ApiResponse(data=tools)


# ── 三层提示词管理接口 ──

@router.get("/system-prompt")
async def get_system_prompt(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    """获取当前系统提示词内容（只读，所有人可看）。"""
    content = await conv_svc.get_system_prompt(db)
    return ApiResponse(data={"content": content})


@router.put("/system-prompt")
async def update_system_prompt(
    payload: UpdatePromptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    """管理员更新系统提示词。"""
    prompt = await conv_svc.update_system_prompt(db, payload.content, user.id)
    return ApiResponse(data={"id": prompt.id, "content": prompt.content, "version": prompt.version})


@router.get("/enterprise-prompt")
async def get_enterprise_prompt(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    """获取当前企业提示词内容。"""
    content = await conv_svc.get_enterprise_prompt(db)
    return ApiResponse(data={"content": content})


@router.put("/enterprise-prompt")
async def update_enterprise_prompt(
    payload: UpdatePromptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    """管理员更新企业提示词。"""
    prompt = await conv_svc.update_enterprise_prompt(db, payload.content, user.id)
    return ApiResponse(data={"id": prompt.id, "content": prompt.content, "version": prompt.version})


@router.get("/user-profile")
async def get_my_profile(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    """获取当前用户的个人画像。"""
    from init_db import ensure_user_profile
    profile = await ensure_user_profile(db, user.id)
    return ApiResponse(data={
        "owner_id": profile.owner_id,
        "profile_data": json.loads(profile.profile_data) if profile.profile_data else {},
        "version": profile.version,
        "evolved_at": profile.evolved_at.isoformat() if profile.evolved_at else None,
        "conversation_count": profile.conversation_count,
    })


# ── 对话接口 ──

@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    items = await conv_svc.list_conversations(db, user.id)
    return ApiResponse(data=[_conversation_payload(item) for item in items])


@router.post("/conversations")
async def create_conversation(payload: CreateConvRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    await run_init(db)
    item = await conv_svc.create_conversation(db, user.id, payload.title)
    return ApiResponse(data=_conversation_payload(item))


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: int,
    payload: RenameConvRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    item = await conv_svc.rename_conversation(db, user.id, conversation_id, payload.title)
    return ApiResponse(data=_conversation_payload(item) if item else None)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data={"deleted": await conv_svc.delete_conversation(db, user.id, conversation_id)})


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=await conv_svc.get_messages_with_meta(db, user.id, conversation_id))


# ── 聊天 ──

@router.post("/chat")
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    from .handlers.chat import handle_chat
    return await handle_chat(payload, db, user)


# ── engine批5：Admin 只读接口（重放 + 概览） ──

@router.get("/admin/replay/{conversation_id}")
async def admin_replay(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_admin_replay
    return await handle_admin_replay(conversation_id, db, user)


@router.get("/admin/overview")
async def admin_overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_admin_overview
    return await handle_admin_overview(db, user)


# ── 敏感操作审批 API ──

@router.get("/admin/approvals/pending")
async def list_approvals(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_list_approvals
    return await handle_list_approvals(db, user)


@router.post("/admin/approvals/{approval_id}/resolve")
async def resolve_approval_endpoint(
    approval_id: int,
    body: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_resolve_approval
    return await handle_resolve_approval(approval_id, body.decision, body.reason, db, user)


# ── Agent Config CRUD (migrated from framework) ──

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


@router.get("/configs")
async def list_agent_configs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from sqlalchemy import select
    from .models import AgentConfig
    r = await db.execute(
        select(AgentConfig).order_by(AgentConfig.agent_code)
    )
    configs = r.scalars().all()
    return ApiResponse(data=[_config_to_dict(c) for c in configs])


@router.get("/configs/{agent_code}")
async def get_agent_config(
    agent_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from sqlalchemy import select
    from .models import AgentConfig
    from app.core.exceptions import NotFound
    r = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_code == agent_code)
    )
    c = r.scalar_one_or_none()
    if not c:
        raise NotFound(f"Agent config '{agent_code}' not found")
    return ApiResponse(data=_config_to_dict(c))


@router.post("/configs")
async def create_agent_config(
    body: AgentConfigCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from sqlalchemy import select
    from .models import AgentConfig
    from app.core.exceptions import ConflictError
    r = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_code == body.agent_code)
    )
    if r.scalar_one_or_none():
        raise ConflictError(f"Agent config '{body.agent_code}' already exists")
    config = AgentConfig(
        agent_code=body.agent_code, agent_name=body.agent_name,
        provider=body.provider, model=body.model,
        system_prompt=body.system_prompt, purpose=body.purpose,
        enabled=body.enabled, temperature=body.temperature,
        top_p=body.top_p, max_tokens=body.max_tokens,
        timeout_ms=body.timeout_ms, fallback_model=body.fallback_model,
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


@router.put("/configs/{agent_code}")
async def update_agent_config(
    agent_code: str,
    body: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from sqlalchemy import select
    from .models import AgentConfig
    from app.core.exceptions import NotFound
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


@router.delete("/configs/{agent_code}")
async def delete_agent_config(
    agent_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from sqlalchemy import select
    from .models import AgentConfig
    from app.core.exceptions import NotFound
    r = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_code == agent_code)
    )
    config = r.scalar_one_or_none()
    if not config:
        raise NotFound(f"Agent config '{agent_code}' not found")
    await db.delete(config)
    await db.commit()
    return ApiResponse(data={"ok": True})


# Import capabilities to register them at module load
# noinspection PyUnresolvedReferences
from .handlers import tool  # noqa: F401, E402
