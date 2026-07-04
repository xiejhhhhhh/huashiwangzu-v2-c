"""Agent workflow capability registration."""

from __future__ import annotations

from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.file_reader import resolve_caller_user_id
from app.services.module_registry import register_capability
from sqlalchemy.ext.asyncio import AsyncSession

from ..init_db import run_init
from ..services import workflow_service as svc


async def _caller_context(db: AsyncSession, caller: str) -> tuple[int, bool]:
    caller_id = resolve_caller_user_id(caller)
    if caller.startswith("system:"):
        return caller_id, True
    user = await db.get(User, caller_id)
    return caller_id, bool(user and user.role == "admin")


async def _cap_create_workflow(params: dict, caller: str) -> dict:
    async with AsyncSessionLocal() as db:
        await run_init(db)
        caller_id, is_admin = await _caller_context(db, caller)
        requested_owner_id = params.get("owner_id")
        owner_id = int(requested_owner_id) if requested_owner_id and is_admin else caller_id
        creator_id = caller_id if caller.startswith("user:") else None
        run = await svc.create_workflow(
            db,
            title=params.get("title", ""),
            intent=params.get("intent", ""),
            source=params.get("source", "manual"),
            owner_id=owner_id,
            creator_id=creator_id,
            extra_meta=params.get("extra_meta") or {},
        )
        return {"workflow_run_id": run.id, "status": run.status}


async def _cap_get_workflow_status(params: dict, caller: str) -> dict:
    run_id = int(params.get("run_id") or params.get("workflow_run_id") or 0)
    async with AsyncSessionLocal() as db:
        owner_id, is_admin = await _caller_context(db, caller)
        run = await svc.get_workflow(db, run_id, user_id=owner_id, is_admin=is_admin)
        return svc.workflow_to_summary(run)


async def _cap_list_workflows(params: dict, caller: str) -> dict:
    async with AsyncSessionLocal() as db:
        owner_id, is_admin = await _caller_context(db, caller)
        runs = await svc.list_workflows(
            db,
            user_id=owner_id,
            is_admin=is_admin,
            status=params.get("status"),
            limit=int(params.get("limit", 50)),
        )
        serializer = svc.workflow_to_admin_dict if is_admin else svc.workflow_to_summary
        return {"items": [serializer(run) for run in runs], "total": len(runs)}


async def _cap_list_workflow_steps(params: dict, caller: str) -> dict:
    run_id = int(params.get("run_id") or params.get("workflow_run_id") or 0)
    async with AsyncSessionLocal() as db:
        owner_id, is_admin = await _caller_context(db, caller)
        await svc.get_workflow(db, run_id, user_id=owner_id, is_admin=is_admin)
        steps = await svc.list_steps(db, run_id)
        return {"items": [svc.step_to_dict(step) for step in steps], "total": len(steps)}


async def _cap_list_workflow_artifacts(params: dict, caller: str) -> dict:
    run_id = int(params.get("run_id") or params.get("workflow_run_id") or 0)
    async with AsyncSessionLocal() as db:
        owner_id, is_admin = await _caller_context(db, caller)
        await svc.get_workflow(db, run_id, user_id=owner_id, is_admin=is_admin)
        artifacts = await svc.list_artifacts(db, run_id)
        visible = artifacts if is_admin else [item for item in artifacts if item.visibility in {"user", "developer"}]
        return {"items": [svc.artifact_to_dict(item) for item in visible], "total": len(visible)}


async def _cap_get_multi_agent_summary(params: dict, caller: str) -> dict:
    run_id = int(params.get("run_id") or params.get("workflow_run_id") or 0)
    async with AsyncSessionLocal() as db:
        owner_id, is_admin = await _caller_context(db, caller)
        await svc.get_workflow(db, run_id, user_id=owner_id, is_admin=is_admin)
        return await svc.get_multi_agent_summary(db, run_id, include_hidden_artifacts=is_admin)


async def _cap_record_workflow_step(params: dict, caller: str) -> dict:
    run_id = int(params.get("run_id") or params.get("workflow_run_id") or 0)
    async with AsyncSessionLocal() as db:
        await svc.ensure_workflow_owner_from_caller(db, run_id, caller)
        step_id = params.get("step_id")
        if step_id:
            step = await svc.update_step_status(
                db,
                int(step_id),
                status=params.get("status", "running"),
                run_id=run_id,
                summary=params.get("summary"),
                output_ref=params.get("output_ref"),
                error_class=params.get("error_class"),
                error_signature=params.get("error_signature"),
            )
        else:
            step = await svc.create_step(
                db,
                run_id=run_id,
                step_key=params.get("step_key", ""),
                title=params.get("title", ""),
                step_type=params.get("type", "agent"),
                order_index=params.get("order_index"),
                input_ref=params.get("input_ref"),
                max_retries=int(params.get("max_retries", 0)),
                extra_meta=params.get("extra_meta") or {},
            )
            if params.get("status"):
                step = await svc.update_step_status(
                    db,
                    step.id,
                    status=params["status"],
                    run_id=run_id,
                    summary=params.get("summary"),
                    output_ref=params.get("output_ref"),
                )
        return {"step": svc.step_to_dict(step)}


async def _cap_record_tool_call(params: dict, caller: str) -> dict:
    run_id = int(params.get("run_id") or params.get("workflow_run_id") or 0)
    async with AsyncSessionLocal() as db:
        await svc.ensure_workflow_owner_from_caller(db, run_id, caller)
        call = await svc.record_tool_call(
            db,
            run_id=run_id,
            step_id=params.get("step_id"),
            tool_name=params.get("tool_name", ""),
            arguments=params.get("arguments"),
            target_module=params.get("target_module"),
            action=params.get("action"),
            caller=params.get("caller") or caller,
            side_effect_level=params.get("side_effect_level", "readonly"),
            approval_policy=params.get("approval_policy", "auto"),
            status=params.get("status", "planned"),
            idempotency_key=params.get("idempotency_key"),
            agent_run_id=params.get("agent_run_id"),
            extra_meta=params.get("extra_meta") or {},
        )
        return {"tool_call": svc.tool_call_to_dict(call, include_arguments=False)}


async def _cap_record_verification(params: dict, caller: str) -> dict:
    run_id = int(params.get("run_id") or params.get("workflow_run_id") or 0)
    async with AsyncSessionLocal() as db:
        await svc.ensure_workflow_owner_from_caller(db, run_id, caller)
        item = await svc.record_verification(
            db,
            run_id=run_id,
            step_id=params.get("step_id"),
            verification_type=params.get("verification_type", ""),
            status=params.get("status", ""),
            command_or_capability=params.get("command_or_capability"),
            evidence_ref=params.get("evidence_ref"),
            summary=params.get("summary"),
            is_required_for_completion=bool(params.get("is_required_for_completion", True)),
            duration_ms=params.get("duration_ms"),
            extra_meta=params.get("extra_meta") or {},
        )
        return {"verification": svc.verification_to_dict(item)}


async def _cap_request_workflow_approval(params: dict, caller: str) -> dict:
    run_id = int(params.get("run_id") or params.get("workflow_run_id") or 0)
    requested_by = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        await svc.ensure_workflow_owner_from_caller(db, run_id, caller)
        approval = await svc.request_approval(
            db,
            run_id=run_id,
            tool_call_id=int(params.get("tool_call_id") or 0),
            requested_by=requested_by,
            agent_code=params.get("agent_code", "default"),
            reason=params.get("reason"),
            request_type=params.get("request_type", "tool_call"),
            risk_level=params.get("risk_level", "dangerous"),
            decision_scope=params.get("decision_scope", "single_call"),
            resume_target=params.get("resume_target"),
        )
        return {
            "approval_id": approval.id,
            "workflow_run_id": approval.workflow_run_id,
            "tool_call_id": approval.tool_call_id,
            "status": approval.status,
            "payload_hash": approval.payload_hash,
            "resume_target": approval.resume_target,
        }


async def _cap_resolve_workflow_approval(params: dict, caller: str) -> dict:
    decided_by = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        return await svc.resolve_approval(
            db,
            approval_id=int(params.get("approval_id") or 0),
            decision=params.get("decision", ""),
            decided_by=decided_by,
            reason=params.get("reason"),
            payload_hash=params.get("payload_hash"),
        )


async def _cap_finalize_workflow(params: dict, caller: str) -> dict:
    run_id = int(params.get("run_id") or params.get("workflow_run_id") or 0)
    async with AsyncSessionLocal() as db:
        await svc.ensure_workflow_owner_from_caller(db, run_id, caller)
        run = await svc.finalize_workflow(
            db,
            run_id=run_id,
            developer_summary=params.get("developer_summary"),
        )
        return svc.workflow_to_summary(run)


capabilities = [
    (
        "agent",
        "create_workflow",
        _cap_create_workflow,
        "创建 Agent 用户级 workflow 账本",
        "创建workflow",
        {
            "title": {"type": "string"},
            "intent": {"type": "string"},
            "source": {"type": "string"},
            "owner_id": {"type": "integer"},
            "extra_meta": {"type": "object"},
        },
        "viewer",
    ),
    (
        "agent",
        "get_workflow_status",
        _cap_get_workflow_status,
        "获取 workflow 极简状态",
        "获取workflow状态",
        {"run_id": {"type": "integer"}},
        "viewer",
    ),
    (
        "agent",
        "list_workflows",
        _cap_list_workflows,
        "列出当前用户 workflow",
        "列出workflow",
        {
            "owner_id": {"type": "integer"},
            "status": {"type": "string"},
            "limit": {"type": "integer"},
            "offset": {"type": "integer"},
        },
        "viewer",
    ),
    (
        "agent",
        "list_workflow_steps",
        _cap_list_workflow_steps,
        "列出 workflow steps",
        "列出workflow步骤",
        {"run_id": {"type": "integer"}},
        "viewer",
    ),
    (
        "agent",
        "list_workflow_artifacts",
        _cap_list_workflow_artifacts,
        "列出 workflow artifacts",
        "列出workflow产物",
        {"run_id": {"type": "integer"}},
        "viewer",
    ),
    (
        "agent",
        "get_multi_agent_summary",
        _cap_get_multi_agent_summary,
        "汇总 workflow 子代理/步骤执行结果",
        "汇总多代理结果",
        {"run_id": {"type": "integer"}},
        "viewer",
    ),
    (
        "agent",
        "record_workflow_step",
        _cap_record_workflow_step,
        "记录或更新 workflow step",
        "记录workflow步骤",
        {
            "run_id": {"type": "integer"},
            "step_key": {"type": "string"},
            "title": {"type": "string"},
            "type": {"type": "string"},
            "status": {"type": "string"},
            "summary": {"type": "string"},
            "extra_meta": {"type": "object"},
        },
        "viewer",
    ),
    (
        "agent",
        "record_tool_call",
        _cap_record_tool_call,
        "记录 workflow tool call",
        "记录workflow工具调用",
        {
            "run_id": {"type": "integer"},
            "step_id": {"type": "integer"},
            "tool_name": {"type": "string"},
            "target_module": {"type": "string"},
            "action": {"type": "string"},
            "arguments": {"type": "object"},
            "side_effect_level": {"type": "string"},
            "approval_policy": {"type": "string"},
            "idempotency_key": {"type": "string"},
        },
        "viewer",
    ),
    (
        "agent",
        "record_verification",
        _cap_record_verification,
        "记录 workflow verification",
        "记录workflow验证",
        {
            "run_id": {"type": "integer"},
            "step_id": {"type": "integer"},
            "verification_type": {"type": "string"},
            "status": {"type": "string"},
            "summary": {"type": "string"},
            "is_required_for_completion": {"type": "boolean"},
        },
        "viewer",
    ),
    (
        "agent",
        "request_workflow_approval",
        _cap_request_workflow_approval,
        "请求 workflow 审批",
        "请求workflow审批",
        {
            "run_id": {"type": "integer"},
            "tool_call_id": {"type": "integer"},
            "request_type": {"type": "string"},
            "risk_level": {"type": "string"},
            "decision_scope": {"type": "string"},
            "resume_target": {"type": "object"},
        },
        "viewer",
    ),
    (
        "agent",
        "resolve_workflow_approval",
        _cap_resolve_workflow_approval,
        "处理 workflow 审批",
        "处理workflow审批",
        {
            "approval_id": {"type": "integer"},
            "decision": {"type": "string"},
            "payload_hash": {"type": "string"},
            "reason": {"type": "string"},
        },
        "admin",
    ),
    (
        "agent",
        "finalize_workflow",
        _cap_finalize_workflow,
        "按 verification 裁判 workflow 终态",
        "裁判workflow终态",
        {
            "run_id": {"type": "integer"},
            "developer_summary": {"type": "string"},
        },
        "viewer",
    ),
]

for _module, _action, _handler, _description, _brief, _parameters, _min_role in capabilities:
    register_capability(
        _module,
        _action,
        _handler,
        description=_description,
        brief=_brief,
        parameters=_parameters or {"run_id": {"type": "integer", "description": "workflow run id"}},
        min_role=_min_role,
    )
