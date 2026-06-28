import json
import logging

logger = logging.getLogger("v2.agent").getChild("router")

from app.database import get_db
from app.gateway.router import gateway_router
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .init_db import (
    ensure_default_agent_prompts,
    run_init,
)
from .runtime import ConversationRuntime
from .schemas import ChatRequest, EditResubmitRequest
from .services import agent_config_service, tool_discovery
from .services import conversation_service as conv_svc
from .services import prompt_service as prompt_svc

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


class UpdatePromptRequest(BaseModel):
    content: str


class ApprovalDecision(BaseModel):
    decision: str  # "approved" | "rejected"
    reason: str | None = None


class PromptItemCreate(BaseModel):
    key: str = ""
    title: str
    category: str
    content: str
    is_active: bool = True
    status: str = "draft"


class PromptItemUpdate(BaseModel):
    key: str | None = None
    title: str | None = None
    category: str | None = None
    content: str | None = None
    is_active: bool | None = None
    status: str | None = None


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
    await run_init(db)
    items = await conv_svc.list_conversations(db, user.id)
    return ApiResponse(data=[_conversation_payload(item) for item in items])


@router.post("/conversations")
async def create_conversation(payload: CreateConvRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    await run_init(db)
    await ensure_default_agent_prompts(db)
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


@router.post("/conversations/{conversation_id}/rollback")
async def rollback_conversation(
    conversation_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    message_id = payload.get("message_id")
    if not message_id:
        return ApiResponse(success=False, error="message_id required")
    ok = await conv_svc.rollback_conversation(db, user.id, conversation_id, message_id)
    return ApiResponse(data={"rolled_back": ok})


@router.post("/conversations/{conversation_id}/messages/{message_id}/edit-resubmit")
async def edit_resubmit(
    conversation_id: int,
    message_id: int,
    payload: EditResubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """Edit a user message in-place and re-run Agent from that point (soft branch).

    Validates ownership and role='user', updates the message content,
    archives messages after the edit point, deletes stale events, then
    runs the tool loop with the edited content as current turn input.
    Returns SSE stream identical to ``/api/agent/chat``.
    """
    if not payload.content or not payload.content.strip():
        return ApiResponse(success=False, error="content is required")
    runtime = ConversationRuntime()
    return await runtime.execute_edit_resubmit(
        conversation_id=conversation_id,
        message_id=message_id,
        content=payload.content,
        profile_key=payload.profile_key or "deepseek-v4-flash",
        db=db,
        user=user,
    )


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=await conv_svc.get_messages_with_meta(db, user.id, conversation_id))


# ── 聊天 ──

@router.post("/chat")
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    runtime = ConversationRuntime()
    if payload.enable_checkpointer is not None:
        runtime.policy.enable_checkpointer = bool(payload.enable_checkpointer)
    return await runtime.execute(payload, db, user)


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


@router.get("/admin/hook-lifecycle")
async def admin_hook_lifecycle(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_admin_hook_lifecycle
    return await handle_admin_hook_lifecycle(db, user)


@router.get("/admin/memory-quality")
async def admin_memory_quality(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .handlers.admin import handle_admin_memory_quality
    return await handle_admin_memory_quality(db, user)


@router.get("/admin/failure-diagnostics")
async def admin_failure_diagnostics(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
    owner_id: int | None = None,
):
    from .engine.failure_diagnostics import read_failure_diagnostics
    diagnostics = await read_failure_diagnostics(limit=limit, owner_id=owner_id)
    return ApiResponse(data={
        "total_returned": len(diagnostics),
        "diagnostics": diagnostics,
    })


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
    await ensure_default_agent_prompts(db)
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
    data = await prompt_svc.update_prompt(
        db,
        user.id,
        prompt_id,
        body.model_dump(exclude_none=True),
        is_admin=user.role == "admin",
    )
    return ApiResponse(data=data)


@router.delete("/prompts/{prompt_id}")
async def delete_agent_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await prompt_svc.delete_prompt(db, user.id, prompt_id)
    return ApiResponse(data=data)


# Import capabilities to register them at module load
# noinspection PyUnresolvedReferences
from .handlers import tool  # noqa: F401, E402
