import json
import logging

from app.core.exceptions import ValidationError
from app.database import get_db
from app.gateway.router import gateway_router
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .bootstrap import register_agent_tasks
from .init_db import (
    ensure_default_agent_prompts,
    run_init,
)
from .schemas import (
    AgentConfigCreate,
    AgentConfigUpdate,
    ApprovalDecision,
    ChatRequest,
    CreateConvRequest,
    EditResubmitRequest,
    PromptItemCreate,
    PromptItemUpdate,
    RenameConvRequest,
    UpdatePromptRequest,
    WorkflowApprovalRequest,
    WorkflowArtifactRequest,
    WorkflowCancelRequest,
    WorkflowCreateRequest,
    WorkflowDemoSeedRequest,
    WorkflowFinalizeRequest,
    WorkflowStepRequest,
    WorkflowToolCallRequest,
    WorkflowVerificationRequest,
)
from .services import agent_config_service, tool_discovery
from .services import conversation_service as conv_svc
from .services import prompt_service as prompt_svc
from .services import workflow_seed_service as workflow_seed_svc
from .services import workflow_service as workflow_svc

logger = logging.getLogger("v2.agent").getChild("router")

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Register background task handlers before the framework worker starts.
register_agent_tasks()


def _j(obj) -> str:
    """json.dumps with datetime fallback."""
    return json.dumps(obj, ensure_ascii=False, default=str)


def _conversation_payload(item) -> dict:
    return {"id": item.id, "title": item.title, "status": item.status}


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
        raise ValidationError("message_id required")
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
        raise ValidationError("content is required")
    from .runtime import ConversationRuntime

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
    from .runtime import ConversationRuntime

    runtime = ConversationRuntime()
    if payload.enable_checkpointer is not None:
        runtime.policy.enable_checkpointer = bool(payload.enable_checkpointer)
    return await runtime.execute(payload, db, user)


# ── Agent workflow center ──

def _is_admin(user: User) -> bool:
    return user.role == "admin"


async def _require_workflow_visible(
    db: AsyncSession,
    run_id: int,
    user: User,
):
    return await workflow_svc.get_workflow(db, run_id, user_id=user.id, is_admin=_is_admin(user))


@router.get("/workflows")
async def list_workflows(
    status: str | None = None,
    has_failures: bool | None = None,
    has_artifacts: bool | None = None,
    has_references: bool | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    runs = await workflow_svc.list_workflows(
        db,
        user_id=user.id,
        is_admin=_is_admin(user),
        status=status,
        limit=limit if not any(item is not None for item in (has_failures, has_artifacts, has_references)) else 200,
    )
    serializer = workflow_svc.workflow_to_admin_dict if _is_admin(user) else workflow_svc.workflow_to_summary
    counts = await workflow_svc.get_workflow_rollup_counts(
        db,
        [run.id for run in runs],
        include_hidden_artifacts=_is_admin(user),
    )
    items = []
    for run in runs:
        item = serializer(run)
        item.update(counts.get(run.id, {}))
        if has_failures is not None and bool(item.get("failure_count")) != has_failures:
            continue
        if has_artifacts is not None and bool(item.get("artifact_count")) != has_artifacts:
            continue
        if has_references is not None and bool(item.get("reference_count")) != has_references:
            continue
        items.append(item)
        if len(items) >= max(1, min(limit, 200)):
            break
    return ApiResponse(data={"items": items, "total": len(items)})


@router.post("/workflows")
async def create_workflow(
    body: WorkflowCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    owner_id = body.owner_id if body.owner_id and _is_admin(user) else user.id
    run = await workflow_svc.create_workflow(
        db,
        title=body.title,
        intent=body.intent,
        source=body.source,
        owner_id=owner_id,
        creator_id=user.id,
        extra_meta=body.extra_meta,
    )
    return ApiResponse(data={"workflow_run_id": run.id, "status": run.status})


@router.get("/workflows/governance-summary")
async def get_workflow_governance_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    return ApiResponse(data=await workflow_svc.get_workflow_governance_summary(
        db,
        owner_id=user.id,
        is_admin=_is_admin(user),
    ))


@router.post("/workflows/demo-seed")
async def seed_demo_workflows(
    body: WorkflowDemoSeedRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    await run_init(db)
    owner_id = body.owner_id or user.id
    return ApiResponse(data=await workflow_seed_svc.seed_demo_workflows(
        db,
        owner_id=owner_id,
        creator_id=user.id,
        marker=body.marker,
        cleanup_existing=body.cleanup_existing,
    ))


@router.post("/workflows/demo-seed/cleanup")
async def cleanup_demo_workflows(
    body: WorkflowDemoSeedRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    await run_init(db)
    return ApiResponse(data=await workflow_seed_svc.cleanup_demo_workflows(db, marker=body.marker))


@router.get("/workflows/{run_id}")
async def get_workflow(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    run = await _require_workflow_visible(db, run_id, user)
    data = workflow_svc.workflow_to_admin_dict(run) if _is_admin(user) else workflow_svc.workflow_to_summary(run)
    steps = await workflow_svc.list_steps(db, run_id)
    tool_calls = await workflow_svc.list_tool_calls(db, run_id)
    artifacts = await workflow_svc.list_artifacts(db, run_id)
    verifications = await workflow_svc.list_verifications(db, run_id)
    failures = await workflow_svc.list_failures(db, run_id)
    if not _is_admin(user):
        artifacts = [item for item in artifacts if item.visibility in {"user", "developer"}]
    data.update({
        "steps": [workflow_svc.step_to_dict(step) for step in steps],
        "tool_calls": [
            workflow_svc.tool_call_to_dict(call, include_arguments=_is_admin(user))
            for call in tool_calls
        ],
        "artifacts": [workflow_svc.artifact_to_dict(item) for item in artifacts],
        "verifications": [workflow_svc.verification_to_dict(item) for item in verifications],
        "failures": [workflow_svc.failure_to_dict(item) for item in failures],
    })
    counts = await workflow_svc.get_workflow_rollup_counts(
        db,
        [run_id],
        include_hidden_artifacts=_is_admin(user),
    )
    data.update(counts.get(run_id, {}))
    data["multi_agent_summary"] = await workflow_svc.get_multi_agent_summary(
        db,
        run_id,
        include_hidden_artifacts=_is_admin(user),
    )
    return ApiResponse(data=data)


@router.get("/workflows/{run_id}/steps")
async def list_workflow_steps(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    steps = await workflow_svc.list_steps(db, run_id)
    return ApiResponse(data={"items": [workflow_svc.step_to_dict(step) for step in steps], "total": len(steps)})


@router.get("/workflows/{run_id}/multi-agent-summary")
async def get_workflow_multi_agent_summary(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    return ApiResponse(data=await workflow_svc.get_multi_agent_summary(
        db,
        run_id,
        include_hidden_artifacts=_is_admin(user),
    ))


@router.post("/workflows/{run_id}/steps")
async def record_workflow_step(
    run_id: int,
    body: WorkflowStepRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    step = await workflow_svc.create_step(
        db,
        run_id=run_id,
        step_key=body.step_key,
        title=body.title,
        step_type=body.type,
        order_index=body.order_index,
        input_ref=body.input_ref,
        max_retries=body.max_retries,
        extra_meta=body.extra_meta,
    )
    if body.status:
        step = await workflow_svc.update_step_status(
            db,
            step.id,
            status=body.status,
            run_id=run_id,
            summary=body.summary,
            output_ref=body.output_ref,
        )
    return ApiResponse(data={"step": workflow_svc.step_to_dict(step)})


@router.get("/workflows/{run_id}/artifacts")
async def list_workflow_artifacts(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    artifacts = await workflow_svc.list_artifacts(db, run_id)
    if not _is_admin(user):
        artifacts = [item for item in artifacts if item.visibility in {"user", "developer"}]
    return ApiResponse(data={"items": [workflow_svc.artifact_to_dict(item) for item in artifacts], "total": len(artifacts)})


@router.post("/workflows/{run_id}/artifacts")
async def create_workflow_artifact(
    run_id: int,
    body: WorkflowArtifactRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    artifact = await workflow_svc.create_artifact(
        db,
        run_id=run_id,
        step_id=body.step_id,
        artifact_type=body.artifact_type,
        storage_kind=body.storage_kind,
        storage_ref=body.storage_ref,
        visibility=body.visibility,
        lifecycle=body.lifecycle,
        ttl_seconds=body.ttl_seconds,
        checksum=body.checksum,
        summary=body.summary,
        extra_meta=body.extra_meta,
    )
    return ApiResponse(data={"artifact": workflow_svc.artifact_to_dict(artifact)})


@router.get("/workflows/{run_id}/verifications")
async def list_workflow_verifications(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    verifications = await workflow_svc.list_verifications(db, run_id)
    return ApiResponse(data={
        "items": [workflow_svc.verification_to_dict(item) for item in verifications],
        "total": len(verifications),
    })


@router.post("/workflows/{run_id}/verifications")
async def record_workflow_verification(
    run_id: int,
    body: WorkflowVerificationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    item = await workflow_svc.record_verification(
        db,
        run_id=run_id,
        step_id=body.step_id,
        verification_type=body.verification_type,
        status=body.status,
        command_or_capability=body.command_or_capability,
        evidence_ref=body.evidence_ref,
        summary=body.summary,
        is_required_for_completion=body.is_required_for_completion,
        duration_ms=body.duration_ms,
        extra_meta=body.extra_meta,
    )
    return ApiResponse(data={"verification": workflow_svc.verification_to_dict(item)})


@router.post("/workflows/{run_id}/tool-calls")
async def record_workflow_tool_call(
    run_id: int,
    body: WorkflowToolCallRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    call = await workflow_svc.record_tool_call(
        db,
        run_id=run_id,
        step_id=body.step_id,
        tool_name=body.tool_name,
        arguments=body.arguments,
        target_module=body.target_module,
        action=body.action,
        caller=body.caller or f"user:{user.id}",
        side_effect_level=body.side_effect_level,
        approval_policy=body.approval_policy,
        status=body.status,
        idempotency_key=body.idempotency_key,
        agent_run_id=body.agent_run_id,
        extra_meta=body.extra_meta,
    )
    return ApiResponse(data={"tool_call": workflow_svc.tool_call_to_dict(call, include_arguments=_is_admin(user))})


@router.get("/workflows/{run_id}/tool-calls")
async def list_workflow_tool_calls(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    calls = await workflow_svc.list_tool_calls(db, run_id)
    return ApiResponse(data={
        "items": [
            workflow_svc.tool_call_to_dict(call, include_arguments=_is_admin(user))
            for call in calls
        ],
        "total": len(calls),
    })


@router.post("/workflows/{run_id}/approvals")
async def request_workflow_approval(
    run_id: int,
    body: WorkflowApprovalRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    approval = await workflow_svc.request_approval(
        db,
        run_id=run_id,
        tool_call_id=body.tool_call_id,
        requested_by=user.id,
        agent_code=body.agent_code,
        reason=body.reason,
        request_type=body.request_type,
        risk_level=body.risk_level,
        decision_scope=body.decision_scope,
        resume_target=body.resume_target,
    )
    return ApiResponse(data={
        "approval_id": approval.id,
        "workflow_run_id": approval.workflow_run_id,
        "workflow_step_id": approval.workflow_step_id,
        "tool_call_id": approval.tool_call_id,
        "status": approval.status,
        "payload_hash": approval.payload_hash,
        "resume_target": approval.resume_target,
    })


@router.post("/workflows/{run_id}/finalize")
async def finalize_workflow(
    run_id: int,
    body: WorkflowFinalizeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    run = await workflow_svc.finalize_workflow(
        db,
        run_id=run_id,
        developer_summary=body.developer_summary,
    )
    return ApiResponse(data=workflow_svc.workflow_to_summary(run))


@router.get("/workflows/{run_id}/failures")
async def list_workflow_failures(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    await _require_workflow_visible(db, run_id, user)
    failures = await workflow_svc.list_failures(db, run_id)
    return ApiResponse(data={
        "items": [workflow_svc.failure_to_dict(item) for item in failures],
        "total": len(failures),
    })


@router.post("/workflows/{run_id}/cancel")
async def cancel_workflow(
    run_id: int,
    body: WorkflowCancelRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_workflow_visible(db, run_id, user)
    run = await workflow_svc.update_workflow_status(
        db,
        run_id,
        status="cancelled",
        terminal_status="cancelled",
        verification_status="skipped",
        progress_summary=body.reason or "已取消",
    )
    return ApiResponse(data=workflow_svc.workflow_to_summary(run))


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


# ── 对外操作授权 API ──

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
    return await handle_resolve_approval(approval_id, body.decision, body.reason, db, user, body.payload_hash)


# ── Agent Config CRUD (migrated from framework) ──


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


# ── Tool Guidance HTTP endpoints ──


@router.get("/tool-guides")
async def list_tool_guides(
    owner_id: int | None = None,
    agent_code: str | None = None,
    tool_name: str | None = None,
    scope: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    from .services import tool_guidance_service as tgs
    guides = await tgs.list_guides(
        db, owner_id=owner_id, agent_code=agent_code,
        tool_name=tool_name, scope=scope, status=status,
    )
    return ApiResponse(data={"guides": guides, "total": len(guides)})


@router.get("/tool-guides/{guide_id}")
async def get_tool_guide(
    guide_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    from .services import tool_guidance_service as tgs
    guide = await tgs.get_guide(db, guide_id)
    return ApiResponse(data={"guide": guide})


@router.post("/tool-guides/propose")
async def propose_tool_guide(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    from .services import tool_guidance_service as tgs
    candidate = await tgs.propose_guide(
        db,
        owner_id=body.get("owner_id"),
        agent_code=body.get("agent_code", "default"),
        tool_name=body.get("tool_name", ""),
        scope=body.get("scope", "agent"),
        title=body.get("title", ""),
        guide_text=body.get("guide_text", ""),
        failure_policy=body.get("failure_policy"),
        acceptance_policy=body.get("acceptance_policy"),
        source=body.get("source", "manual"),
        proposed_by=user.id,
        source_trajectory_id=body.get("source_trajectory_id"),
    )
    return ApiResponse(data={"candidate": candidate})


@router.post("/tool-guides/{guide_id}/activate")
async def activate_tool_guide(
    guide_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .services import tool_guidance_service as tgs
    guide = await tgs.activate_guide(db, guide_id, activated_by=user.id)
    return ApiResponse(data={"guide": guide})


@router.post("/tool-guides/{guide_id}/disable")
async def disable_tool_guide(
    guide_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .services import tool_guidance_service as tgs
    guide = await tgs.disable_guide(db, guide_id, disabled_by=user.id)
    return ApiResponse(data={"guide": guide})


@router.post("/tool-guides/{guide_id}/rollback")
async def rollback_tool_guide(
    guide_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    from .services import tool_guidance_service as tgs
    version = body.get("version")
    if not version:
        raise ValidationError("version is required")
    guide = await tgs.rollback_guide(db, guide_id, int(version), rolled_back_by=user.id)
    return ApiResponse(data={"guide": guide})


@router.post("/render-tool-guidance")
async def render_tool_guidance(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    from .services import tool_guidance_service as tgs
    guidance = await tgs.render_tool_guidance(
        db,
        owner_id=user.id,
        agent_code=body.get("agent_code", "default"),
        tool_names=body.get("tool_names", []),
        max_tokens=body.get("max_tokens", 2048),
    )
    return ApiResponse(data={"guidance": guidance, "tool_names": body.get("tool_names", [])})


# Import capabilities to register them at module load
# noinspection PyUnresolvedReferences
from .handlers import (
    tool,  # noqa: F401, E402
    tool_guidance,  # noqa: F401, E402
    workflow,  # noqa: F401, E402
)
