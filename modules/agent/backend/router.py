"""Agent module API router.

Routing only — initialization, task registration, and capability registration
are handled by ``bootstrap.py`` (imported once at module load)."""

import json
import logging

logger = logging.getLogger("v2.agent").getChild("router")

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.gateway import service as gateway_service
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse

from .bootstrap import init_agent_module
from .schemas import (
    CreateConvRequest, RenameConvRequest, ChatRequest,
    UpdatePromptRequest, ApprovalDecision,
    PromptItemCreate, PromptItemUpdate,
    AgentConfigCreate, AgentConfigUpdate,
)
from .services import conversation_service as conv_svc
from .services import agent_config_service
from .services import prompt_service as prompt_svc
from .services import tool_discovery

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Bootstrap: init tables, register tasks & capabilities (runs once at import time)
init_agent_module()


def _conversation_payload(item) -> dict:
    return {"id": item.id, "title": item.title, "status": item.status}


# ── Health / Profiles / Tools ──

@router.get("/health")
async def health():
    return ApiResponse(data={"module": "agent", "status": "ok"})


@router.get("/profiles")
async def list_profiles(user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=gateway_service.list_model_profiles())


@router.get("/tools")
async def list_tools(user: User = Depends(require_permission("viewer"))):
    tools = tool_discovery.build_tools(user.role)
    return ApiResponse(data=tools)


# ── 三层提示词管理接口 ──

@router.get("/system-prompt")
async def get_system_prompt(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    content = await conv_svc.get_system_prompt(db)
    return ApiResponse(data={"content": content})


@router.put("/system-prompt")
async def update_system_prompt(
    payload: UpdatePromptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    prompt = await conv_svc.update_system_prompt(db, payload.content, user.id)
    return ApiResponse(data={"id": prompt.id, "content": prompt.content, "version": prompt.version})


@router.get("/enterprise-prompt")
async def get_enterprise_prompt(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    content = await conv_svc.get_enterprise_prompt(db)
    return ApiResponse(data={"content": content})


@router.put("/enterprise-prompt")
async def update_enterprise_prompt(
    payload: UpdatePromptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    prompt = await conv_svc.update_enterprise_prompt(db, payload.content, user.id)
    return ApiResponse(data={"id": prompt.id, "content": prompt.content, "version": prompt.version})


@router.get("/user-profile")
async def get_my_profile(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    from .init_db import ensure_user_profile
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


# ── Admin 只读接口（重放 + 概览） ──

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


@router.get("/admin/hook-lifecycle")
async def admin_hook_lifecycle(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
    owner_id: int | None = None,
):
    from .handlers.admin import handle_admin_hook_lifecycle
    return await handle_admin_hook_lifecycle(db, user, owner_id=owner_id)


@router.get("/admin/failure-diagnostics")
async def admin_failure_diagnostics(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
    owner_id: int | None = None,
):
    from .handlers.admin import handle_admin_failure_diagnostics
    return await handle_admin_failure_diagnostics(db, user, limit=limit, owner_id=owner_id)


@router.get("/admin/memory-quality")
async def admin_memory_quality(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
    owner_id: int | None = None,
):
    from .handlers.admin import handle_admin_memory_quality
    return await handle_admin_memory_quality(db, user, owner_id=owner_id)


@router.get("/admin/snapshots/{conversation_id}")
async def admin_snapshots(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_admin_snapshots
    return await handle_admin_snapshots(conversation_id, db, user)


@router.get("/admin/compression-chain/{conversation_id}")
async def admin_compression_chain(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_admin_compression_chain
    return await handle_admin_compression_chain(conversation_id, db, user)


@router.get("/admin/snapshots/{snapshot_id}/restore")
async def admin_snapshot_restore(
    snapshot_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_admin_snapshot_restore
    return await handle_admin_snapshot_restore(snapshot_id, db, user)


@router.get("/admin/lifecycle-chain/{conversation_id}")
async def admin_lifecycle_chain(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_admin_lifecycle_chain
    return await handle_admin_lifecycle_chain(conversation_id, db, user)


@router.get("/admin/signal-summary")
async def admin_signal_summary(
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_admin_signal_summary
    return await handle_admin_signal_summary(user)


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


# ── Agent Config CRUD ──

@router.get("/configs")
async def list_agent_configs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    data = await agent_config_service.list_configs(db)
    return ApiResponse(data=data)


@router.get("/configs/{agent_code}")
async def get_agent_config(
    agent_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    data = await agent_config_service.get_config(db, agent_code)
    return ApiResponse(data=data)


@router.post("/configs")
async def create_agent_config(
    body: AgentConfigCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    data = await agent_config_service.create_config(db, body.model_dump(), user.id)
    return ApiResponse(data=data)


@router.put("/configs/{agent_code}")
async def update_agent_config(
    agent_code: str,
    body: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    data = await agent_config_service.update_config(db, agent_code, body.model_dump(exclude_none=True), user.id)
    return ApiResponse(data=data)


@router.delete("/configs/{agent_code}")
async def delete_agent_config(
    agent_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    data = await agent_config_service.delete_config(db, agent_code)
    return ApiResponse(data=data)


# ── Agent Prompts CRUD ──

@router.get("/prompts")
async def list_agent_prompts(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await prompt_svc.list_prompts(db, user.id, category)
    return ApiResponse(data=data)


@router.get("/prompts/{prompt_id}")
async def get_agent_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await prompt_svc.get_prompt(db, user.id, prompt_id)
    return ApiResponse(data=data)


@router.post("/prompts")
async def create_agent_prompt(
    body: PromptItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await prompt_svc.create_prompt(db, user.id, body.model_dump())
    return ApiResponse(data=data)


@router.put("/prompts/{prompt_id}")
async def update_agent_prompt(
    prompt_id: int,
    body: PromptItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await prompt_svc.update_prompt(db, user.id, prompt_id, body.model_dump(exclude_none=True))
    return ApiResponse(data=data)


@router.delete("/prompts/{prompt_id}")
async def delete_agent_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await prompt_svc.delete_prompt(db, user.id, prompt_id)
    return ApiResponse(data=data)
