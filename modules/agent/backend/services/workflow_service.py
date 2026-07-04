"""Service layer for the Agent workflow ledger."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ApprovalQueue
from ..services.action_policy import _sanitize_tool_arg_value
from ..workflow_models import (
    AgentFailureRecord,
    AgentToolCall,
    AgentVerificationResult,
    AgentWorkflowArtifact,
    AgentWorkflowRun,
    AgentWorkflowStep,
)

RUN_STATUSES = {
    "waiting",
    "processing",
    "needs_confirmation",
    "completed",
    "failed",
    "partial",
    "cancelled",
    "manual_required",
}
TERMINAL_STATUSES = {
    "clean_completed",
    "completed_with_debt",
    "failed_verified",
    "manual_required",
    "cancelled",
}
VERIFICATION_STATUSES = {"pending", "pass", "fail", "debt", "skipped"}
STEP_STATUSES = {"pending", "running", "paused", "completed", "failed", "skipped", "cancelled"}
TOOL_CALL_STATUSES = {
    "planned",
    "waiting_approval",
    "running",
    "completed",
    "failed",
    "interrupted",
    "blocked",
    "rejected",
}
TERMINAL_RUN_STATUSES = {"completed", "failed", "partial", "cancelled", "manual_required"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_hash(value: Any) -> str:
    payload = json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _summary_ref(value: Any) -> dict:
    return {
        "summary": _sanitize_tool_arg_value(value if value is not None else {}),
        "storage": "sanitized_summary",
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _caller_user_id(caller: str | None) -> int | None:
    if not caller or not caller.startswith("user:"):
        return None
    try:
        return int(caller.split(":", 1)[1])
    except ValueError:
        return None


async def _get_run(db: AsyncSession, run_id: int) -> AgentWorkflowRun:
    run = await db.get(AgentWorkflowRun, run_id)
    if not run:
        raise NotFound(f"Workflow run {run_id} not found")
    return run


async def _get_tool_call(db: AsyncSession, tool_call_id: int) -> AgentToolCall:
    call = await db.get(AgentToolCall, tool_call_id)
    if not call:
        raise NotFound(f"Tool call {tool_call_id} not found")
    return call


async def _get_step(db: AsyncSession, step_id: int) -> AgentWorkflowStep:
    step = await db.get(AgentWorkflowStep, step_id)
    if not step:
        raise NotFound(f"Workflow step {step_id} not found")
    return step


def _assert_step_in_run(step: AgentWorkflowStep, run_id: int) -> None:
    if step.run_id != run_id:
        raise PermissionDenied("Workflow step does not belong to this run")


def _assert_tool_call_in_run(call: AgentToolCall, run_id: int) -> None:
    if call.run_id != run_id:
        raise PermissionDenied("Tool call does not belong to this workflow run")


async def _assert_optional_step_in_run(
    db: AsyncSession,
    step_id: int | None,
    run_id: int,
) -> None:
    if step_id is None:
        return
    step = await _get_step(db, step_id)
    _assert_step_in_run(step, run_id)


def _assert_run_visible(run: AgentWorkflowRun, user_id: int, is_admin: bool) -> None:
    if not is_admin and run.owner_id != user_id:
        raise PermissionDenied("Workflow is not visible to current user")


def workflow_to_summary(run: AgentWorkflowRun) -> dict:
    return {
        "id": run.id,
        "title": run.title,
        "source": run.source,
        "status": run.status,
        "terminal_status": run.terminal_status,
        "verification_status": run.verification_status,
        "progress_summary": run.progress_summary,
        "needs_confirmation": run.status == "needs_confirmation",
        "artifact_summary": run.artifact_summary or {},
        "updated_at": _iso(run.updated_at),
    }


def workflow_to_admin_dict(run: AgentWorkflowRun) -> dict:
    data = workflow_to_summary(run)
    data.update({
        "owner_id": run.owner_id,
        "creator_id": run.creator_id,
        "intent": run.intent,
        "current_step_id": run.current_step_id,
        "developer_summary": run.developer_summary,
        "dirty_worktree_state": run.dirty_worktree_state,
        "release_gate_verdict": run.release_gate_verdict,
        "queue_task_ids": run.queue_task_ids or [],
        "extra_meta": run.extra_meta or {},
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "created_at": _iso(run.created_at),
    })
    return data


def step_to_dict(step: AgentWorkflowStep) -> dict:
    return {
        "id": step.id,
        "run_id": step.run_id,
        "step_key": step.step_key,
        "title": step.title,
        "type": step.type,
        "status": step.status,
        "order_index": step.order_index,
        "input_ref": step.input_ref,
        "output_ref": step.output_ref,
        "retry_count": step.retry_count,
        "max_retries": step.max_retries,
        "error_class": step.error_class,
        "error_signature": step.error_signature,
        "summary": step.summary,
        "started_at": _iso(step.started_at),
        "finished_at": _iso(step.finished_at),
        "extra_meta": step.extra_meta or {},
        "created_at": _iso(step.created_at),
        "updated_at": _iso(step.updated_at),
    }


def tool_call_to_dict(call: AgentToolCall, include_arguments: bool = False) -> dict:
    data = {
        "id": call.id,
        "run_id": call.run_id,
        "step_id": call.step_id,
        "agent_run_id": call.agent_run_id,
        "tool_name": call.tool_name,
        "target_module": call.target_module,
        "action": call.action,
        "caller": call.caller,
        "arguments_hash": call.arguments_hash,
        "side_effect_level": call.side_effect_level,
        "approval_policy": call.approval_policy,
        "status": call.status,
        "idempotency_key": call.idempotency_key,
        "result_ref": call.result_ref,
        "error_class": call.error_class,
        "error_signature": call.error_signature,
        "started_at": _iso(call.started_at),
        "finished_at": _iso(call.finished_at),
        "extra_meta": call.extra_meta or {},
        "created_at": _iso(call.created_at),
        "updated_at": _iso(call.updated_at),
    }
    if include_arguments:
        data["arguments_ref"] = call.arguments_ref
    return data


def artifact_to_dict(artifact: AgentWorkflowArtifact) -> dict:
    return {
        "id": artifact.id,
        "run_id": artifact.run_id,
        "step_id": artifact.step_id,
        "artifact_type": artifact.artifact_type,
        "storage_kind": artifact.storage_kind,
        "storage_ref": artifact.storage_ref,
        "visibility": artifact.visibility,
        "lifecycle": artifact.lifecycle,
        "ttl_seconds": artifact.ttl_seconds,
        "checksum": artifact.checksum,
        "summary": artifact.summary,
        "extra_meta": artifact.extra_meta or {},
        "created_at": _iso(artifact.created_at),
        "updated_at": _iso(artifact.updated_at),
    }


def verification_to_dict(item: AgentVerificationResult) -> dict:
    return {
        "id": item.id,
        "run_id": item.run_id,
        "step_id": item.step_id,
        "verification_type": item.verification_type,
        "status": item.status,
        "command_or_capability": item.command_or_capability,
        "evidence_ref": item.evidence_ref,
        "summary": item.summary,
        "is_required_for_completion": item.is_required_for_completion,
        "duration_ms": item.duration_ms,
        "extra_meta": item.extra_meta or {},
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def failure_to_dict(item: AgentFailureRecord) -> dict:
    return {
        "id": item.id,
        "run_id": item.run_id,
        "step_id": item.step_id,
        "tool_call_id": item.tool_call_id,
        "failure_type": item.failure_type,
        "error_signature": item.error_signature,
        "retryable": item.retryable,
        "retry_count": item.retry_count,
        "next_action": item.next_action,
        "evidence_ref": item.evidence_ref,
        "handoff_note": item.handoff_note,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


async def create_workflow(
    db: AsyncSession,
    *,
    title: str,
    intent: str,
    source: str,
    owner_id: int,
    creator_id: int | None = None,
    extra_meta: dict | None = None,
) -> AgentWorkflowRun:
    if not title.strip():
        raise ValidationError("title is required")
    run = AgentWorkflowRun(
        owner_id=owner_id,
        creator_id=creator_id,
        source=source or "manual",
        title=title.strip(),
        intent=intent or "",
        status="waiting",
        verification_status="pending",
        progress_summary="等待中",
        extra_meta=extra_meta or {},
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def get_workflow(db: AsyncSession, run_id: int, *, user_id: int, is_admin: bool = False) -> AgentWorkflowRun:
    run = await _get_run(db, run_id)
    _assert_run_visible(run, user_id, is_admin)
    return run


async def list_workflows(
    db: AsyncSession,
    *,
    user_id: int,
    is_admin: bool = False,
    status: str | None = None,
    limit: int = 50,
) -> list[AgentWorkflowRun]:
    stmt = select(AgentWorkflowRun)
    if not is_admin:
        stmt = stmt.where(AgentWorkflowRun.owner_id == user_id)
    if status:
        stmt = stmt.where(AgentWorkflowRun.status == status)
    stmt = stmt.order_by(AgentWorkflowRun.id.desc()).limit(max(1, min(limit, 200)))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def start_workflow(db: AsyncSession, run_id: int, *, progress_summary: str | None = None) -> AgentWorkflowRun:
    run = await _get_run(db, run_id)
    if run.status != "waiting":
        raise ValidationError("Only waiting workflow can be started")
    run.status = "processing"
    run.started_at = run.started_at or _now()
    run.progress_summary = progress_summary or "处理中"
    await db.commit()
    await db.refresh(run)
    return run


async def update_workflow_status(
    db: AsyncSession,
    run_id: int,
    *,
    status: str,
    progress_summary: str | None = None,
    terminal_status: str | None = None,
    verification_status: str | None = None,
    developer_summary: str | None = None,
) -> AgentWorkflowRun:
    if status not in RUN_STATUSES:
        raise ValidationError(f"Invalid workflow status: {status}")
    if terminal_status and terminal_status not in TERMINAL_STATUSES:
        raise ValidationError(f"Invalid terminal status: {terminal_status}")
    if verification_status and verification_status not in VERIFICATION_STATUSES:
        raise ValidationError(f"Invalid verification status: {verification_status}")
    run = await _get_run(db, run_id)
    run.status = status
    if progress_summary is not None:
        run.progress_summary = progress_summary
    if terminal_status is not None:
        run.terminal_status = terminal_status
    if verification_status is not None:
        run.verification_status = verification_status
    if developer_summary is not None:
        run.developer_summary = developer_summary
    if status in TERMINAL_RUN_STATUSES:
        run.finished_at = run.finished_at or _now()
    await db.commit()
    await db.refresh(run)
    return run


async def create_step(
    db: AsyncSession,
    *,
    run_id: int,
    step_key: str,
    title: str,
    step_type: str,
    order_index: int | None = None,
    input_ref: dict | None = None,
    max_retries: int = 0,
    extra_meta: dict | None = None,
) -> AgentWorkflowStep:
    run = await _get_run(db, run_id)
    if order_index is None:
        order_index = int(await db.scalar(
            select(func.coalesce(func.max(AgentWorkflowStep.order_index), 0) + 1)
            .where(AgentWorkflowStep.run_id == run_id)
        ) or 1)
    step = AgentWorkflowStep(
        run_id=run_id,
        step_key=step_key,
        title=title,
        type=step_type,
        status="pending",
        order_index=order_index,
        input_ref=input_ref,
        max_retries=max_retries,
        extra_meta=extra_meta or {},
    )
    db.add(step)
    await db.flush()
    run.current_step_id = step.id
    await db.commit()
    await db.refresh(step)
    return step


async def update_step_status(
    db: AsyncSession,
    step_id: int,
    *,
    status: str,
    run_id: int | None = None,
    summary: str | None = None,
    output_ref: dict | None = None,
    error_class: str | None = None,
    error_signature: str | None = None,
) -> AgentWorkflowStep:
    if status not in STEP_STATUSES:
        raise ValidationError(f"Invalid step status: {status}")
    step = await _get_step(db, step_id)
    if run_id is not None:
        _assert_step_in_run(step, run_id)
    step.status = status
    if status == "running":
        step.started_at = step.started_at or _now()
    if status in {"completed", "failed", "skipped", "cancelled"}:
        step.finished_at = step.finished_at or _now()
    if summary is not None:
        step.summary = summary
    if output_ref is not None:
        step.output_ref = output_ref
    if error_class is not None:
        step.error_class = error_class
    if error_signature is not None:
        step.error_signature = error_signature
    await db.commit()
    await db.refresh(step)
    return step


async def record_tool_call(
    db: AsyncSession,
    *,
    run_id: int,
    step_id: int | None,
    tool_name: str,
    arguments: Any | None = None,
    target_module: str | None = None,
    action: str | None = None,
    caller: str | None = None,
    side_effect_level: str = "readonly",
    approval_policy: str = "auto",
    status: str = "planned",
    idempotency_key: str | None = None,
    agent_run_id: str | None = None,
    extra_meta: dict | None = None,
) -> AgentToolCall:
    await _get_run(db, run_id)
    await _assert_optional_step_in_run(db, step_id, run_id)
    if status not in TOOL_CALL_STATUSES:
        raise ValidationError(f"Invalid tool call status: {status}")
    if "__" in tool_name and (not target_module or not action):
        module, capability = tool_name.split("__", 1)
        target_module = target_module or module
        action = action or capability
    if side_effect_level != "readonly" and not idempotency_key:
        idempotency_key = f"agent-workflow-{run_id}-{uuid.uuid4().hex}"
    call = AgentToolCall(
        run_id=run_id,
        step_id=step_id,
        agent_run_id=agent_run_id,
        tool_name=tool_name,
        target_module=target_module,
        action=action,
        caller=caller,
        arguments_ref=_summary_ref(arguments),
        arguments_hash=_json_hash(arguments),
        side_effect_level=side_effect_level,
        approval_policy=approval_policy,
        status=status,
        idempotency_key=idempotency_key,
        extra_meta=extra_meta or {},
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)
    return call


async def update_tool_call_status(
    db: AsyncSession,
    tool_call_id: int,
    *,
    status: str,
    result_ref: dict | None = None,
    error_class: str | None = None,
    error_signature: str | None = None,
) -> AgentToolCall:
    if status not in TOOL_CALL_STATUSES:
        raise ValidationError(f"Invalid tool call status: {status}")
    call = await _get_tool_call(db, tool_call_id)
    call.status = status
    if status == "running":
        call.started_at = call.started_at or _now()
    if status in {"completed", "failed", "interrupted", "blocked", "rejected"}:
        call.finished_at = call.finished_at or _now()
    if result_ref is not None:
        call.result_ref = result_ref
    if error_class is not None:
        call.error_class = error_class
    if error_signature is not None:
        call.error_signature = error_signature
    await db.commit()
    await db.refresh(call)
    return call


async def create_artifact(
    db: AsyncSession,
    *,
    run_id: int,
    step_id: int | None,
    artifact_type: str,
    storage_kind: str,
    storage_ref: dict | str | None = None,
    visibility: str = "user",
    lifecycle: str = "candidate",
    ttl_seconds: int | None = None,
    checksum: str | None = None,
    summary: str | None = None,
    extra_meta: dict | None = None,
) -> AgentWorkflowArtifact:
    run = await _get_run(db, run_id)
    await _assert_optional_step_in_run(db, step_id, run_id)
    artifact = AgentWorkflowArtifact(
        run_id=run_id,
        step_id=step_id,
        artifact_type=artifact_type,
        storage_kind=storage_kind,
        storage_ref=storage_ref,
        visibility=visibility,
        lifecycle=lifecycle,
        ttl_seconds=ttl_seconds,
        checksum=checksum,
        summary=summary,
        extra_meta=extra_meta or {},
    )
    db.add(artifact)
    summary_map = dict(run.artifact_summary or {})
    summary_map[artifact_type] = summary or storage_kind
    run.artifact_summary = summary_map
    await db.commit()
    await db.refresh(artifact)
    return artifact


async def record_verification(
    db: AsyncSession,
    *,
    run_id: int,
    verification_type: str,
    status: str,
    step_id: int | None = None,
    command_or_capability: str | None = None,
    evidence_ref: dict | None = None,
    summary: str | None = None,
    is_required_for_completion: bool = True,
    duration_ms: int | None = None,
    extra_meta: dict | None = None,
) -> AgentVerificationResult:
    if status not in {"pass", "fail", "debt", "skipped", "not_applicable"}:
        raise ValidationError(f"Invalid verification status: {status}")
    run = await _get_run(db, run_id)
    await _assert_optional_step_in_run(db, step_id, run_id)
    item = AgentVerificationResult(
        run_id=run_id,
        step_id=step_id,
        verification_type=verification_type,
        status=status,
        command_or_capability=command_or_capability,
        evidence_ref=evidence_ref,
        summary=summary,
        is_required_for_completion=is_required_for_completion,
        duration_ms=duration_ms,
        extra_meta=extra_meta or {},
    )
    db.add(item)
    if status == "fail":
        run.verification_status = "fail"
    elif status == "debt":
        run.verification_status = "debt"
    elif run.verification_status == "pending" and status == "pass":
        run.verification_status = "pass"
    if verification_type == "release_gate" and summary and "PASS_WITH_DEBT" in summary:
        run.release_gate_verdict = "PASS_WITH_DEBT"
        run.verification_status = "debt"
    await db.commit()
    await db.refresh(item)
    return item


async def record_failure(
    db: AsyncSession,
    *,
    run_id: int,
    failure_type: str,
    step_id: int | None = None,
    tool_call_id: int | None = None,
    error_signature: str | None = None,
    retryable: bool = False,
    retry_count: int = 0,
    next_action: str = "manual",
    evidence_ref: dict | None = None,
    handoff_note: str | None = None,
) -> AgentFailureRecord:
    await _get_run(db, run_id)
    await _assert_optional_step_in_run(db, step_id, run_id)
    if tool_call_id is not None:
        call = await _get_tool_call(db, tool_call_id)
        _assert_tool_call_in_run(call, run_id)
    item = AgentFailureRecord(
        run_id=run_id,
        step_id=step_id,
        tool_call_id=tool_call_id,
        failure_type=failure_type,
        error_signature=error_signature,
        retryable=retryable,
        retry_count=retry_count,
        next_action=next_action,
        evidence_ref=evidence_ref,
        handoff_note=handoff_note,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def request_approval(
    db: AsyncSession,
    *,
    run_id: int,
    tool_call_id: int,
    requested_by: int,
    agent_code: str = "default",
    reason: str | None = None,
    request_type: str = "tool_call",
    risk_level: str = "dangerous",
    decision_scope: str = "single_call",
    resume_target: dict | None = None,
    expires_at: datetime | None = None,
) -> ApprovalQueue:
    run = await _get_run(db, run_id)
    call = await _get_tool_call(db, tool_call_id)
    _assert_tool_call_in_run(call, run_id)
    await _assert_optional_step_in_run(db, call.step_id, run_id)
    approval = ApprovalQueue(
        agent_code=agent_code,
        tool_name=call.tool_name,
        tool_args=json.dumps(call.arguments_ref or {}, ensure_ascii=False, default=str),
        status="pending",
        requested_by=requested_by,
        reason=reason,
        workflow_run_id=run_id,
        workflow_step_id=call.step_id,
        tool_call_id=tool_call_id,
        request_type=request_type,
        risk_level=risk_level,
        decision_scope=decision_scope,
        payload_hash=call.arguments_hash,
        resume_target=resume_target or {
            "workflow_run_id": run_id,
            "workflow_step_id": call.step_id,
            "tool_call_id": tool_call_id,
            "idempotency_key": call.idempotency_key,
        },
        expires_at=expires_at,
    )
    db.add(approval)
    run.status = "needs_confirmation"
    run.progress_summary = "需要确认"
    if call.step_id:
        step = await db.get(AgentWorkflowStep, call.step_id)
        if step:
            step.status = "paused"
    call.status = "waiting_approval"
    await db.commit()
    await db.refresh(approval)
    return approval


async def resolve_approval(
    db: AsyncSession,
    *,
    approval_id: int,
    decision: str,
    decided_by: int,
    reason: str | None = None,
    payload_hash: str | None = None,
) -> dict:
    if decision not in {"approved", "rejected"}:
        raise ValidationError("decision must be approved or rejected")
    approval = await db.get(ApprovalQueue, approval_id)
    if not approval:
        raise NotFound(f"Approval {approval_id} not found")
    if approval.status != "pending":
        raise ValidationError(f"Approval {approval_id} already {approval.status}")
    if payload_hash and approval.payload_hash and payload_hash != approval.payload_hash:
        decision = "rejected"
        reason = reason or "payload_hash mismatch"

    approval.status = decision
    approval.decided_by = decided_by
    approval.reason = reason
    approval.decided_at = _now()

    run: AgentWorkflowRun | None = None
    call: AgentToolCall | None = None
    if approval.workflow_run_id:
        run = await db.get(AgentWorkflowRun, approval.workflow_run_id)
    if approval.tool_call_id:
        call = await db.get(AgentToolCall, approval.tool_call_id)

    if decision == "approved":
        if call:
            call.status = "planned"
        if approval.workflow_step_id:
            step = await db.get(AgentWorkflowStep, approval.workflow_step_id)
            if step and step.status == "paused":
                step.status = "running"
                step.started_at = step.started_at or _now()
        if run:
            run.status = "processing"
            run.progress_summary = "处理中"
    else:
        if call:
            call.status = "rejected"
            call.finished_at = call.finished_at or _now()
        if run:
            db.add(AgentVerificationResult(
                run_id=run.id,
                step_id=approval.workflow_step_id,
                verification_type="manual_review",
                status="fail",
                summary=reason or "Approval rejected",
                is_required_for_completion=True,
            ))
            run.status = "failed"
            run.terminal_status = "failed_verified"
            run.verification_status = "fail"
            run.finished_at = run.finished_at or _now()
            run.progress_summary = reason or "确认被拒绝"
            db.add(AgentFailureRecord(
                run_id=run.id,
                step_id=approval.workflow_step_id,
                tool_call_id=approval.tool_call_id,
                failure_type="approval_rejected",
                error_signature=reason,
                retryable=False,
                next_action="manual",
                handoff_note=reason,
            ))
    await db.commit()
    return {
        "id": approval.id,
        "status": approval.status,
        "workflow_run_id": approval.workflow_run_id,
        "workflow_step_id": approval.workflow_step_id,
        "tool_call_id": approval.tool_call_id,
        "resume_target": approval.resume_target,
    }


async def finalize_workflow(
    db: AsyncSession,
    *,
    run_id: int,
    developer_summary: str | None = None,
) -> AgentWorkflowRun:
    run = await _get_run(db, run_id)
    verifications = list((await db.execute(
        select(AgentVerificationResult).where(AgentVerificationResult.run_id == run_id)
    )).scalars().all())
    if not verifications:
        raise ValidationError("Workflow cannot finalize without verification result")

    pending_approval_count = await db.scalar(
        select(func.count(ApprovalQueue.id)).where(
            ApprovalQueue.workflow_run_id == run_id,
            ApprovalQueue.status == "pending",
        )
    )
    required = [v for v in verifications if v.is_required_for_completion]
    has_required_fail = any(v.status == "fail" for v in required)
    has_required_debt = any(v.status == "debt" for v in required)
    has_required_skipped = any(v.status in {"skipped", "not_applicable"} for v in required)
    has_optional_debt = any(
        (not v.is_required_for_completion) and v.status in {"debt", "skipped"}
        for v in verifications
    )
    has_debt = has_required_debt or has_optional_debt or run.release_gate_verdict == "PASS_WITH_DEBT"

    if pending_approval_count:
        db.add(AgentVerificationResult(
            run_id=run_id,
            verification_type="manual_review",
            status="skipped",
            summary="Pending approval remains at finalize",
            is_required_for_completion=True,
        ))
        run.status = "manual_required"
        run.terminal_status = "manual_required"
        run.verification_status = "skipped"
        run.progress_summary = "仍有确认未处理"
    elif has_required_fail:
        run.status = "failed"
        run.terminal_status = "failed_verified"
        run.verification_status = "fail"
        run.progress_summary = "验证失败"
        exists = await db.scalar(
            select(func.count(AgentFailureRecord.id)).where(AgentFailureRecord.run_id == run_id)
        )
        if not exists:
            db.add(AgentFailureRecord(
                run_id=run_id,
                failure_type="test_failure",
                error_signature="required verification failed",
                retryable=False,
                next_action="manual",
            ))
    elif has_required_skipped:
        if not any(v.verification_type == "manual_review" for v in verifications):
            db.add(AgentVerificationResult(
                run_id=run_id,
                verification_type="manual_review",
                status="skipped",
                summary="Required verification was skipped",
                is_required_for_completion=True,
            ))
        run.status = "manual_required"
        run.terminal_status = "manual_required"
        run.verification_status = "skipped"
        run.progress_summary = "必要验证未完成"
    elif has_debt:
        run.status = "partial"
        run.terminal_status = "completed_with_debt"
        run.verification_status = "debt"
        run.progress_summary = "部分完成/有债务"
    else:
        run.status = "completed"
        run.terminal_status = "clean_completed"
        run.verification_status = "pass"
        run.progress_summary = "已完成"
    if developer_summary is not None:
        run.developer_summary = developer_summary
    run.finished_at = run.finished_at or _now()
    await db.commit()
    await db.refresh(run)
    return run


async def list_steps(db: AsyncSession, run_id: int) -> list[AgentWorkflowStep]:
    result = await db.execute(
        select(AgentWorkflowStep)
        .where(AgentWorkflowStep.run_id == run_id)
        .order_by(AgentWorkflowStep.order_index, AgentWorkflowStep.id)
    )
    return list(result.scalars().all())


async def list_artifacts(db: AsyncSession, run_id: int) -> list[AgentWorkflowArtifact]:
    result = await db.execute(
        select(AgentWorkflowArtifact)
        .where(AgentWorkflowArtifact.run_id == run_id)
        .order_by(AgentWorkflowArtifact.id)
    )
    return list(result.scalars().all())


async def list_verifications(db: AsyncSession, run_id: int) -> list[AgentVerificationResult]:
    result = await db.execute(
        select(AgentVerificationResult)
        .where(AgentVerificationResult.run_id == run_id)
        .order_by(AgentVerificationResult.id)
    )
    return list(result.scalars().all())


async def list_tool_calls(db: AsyncSession, run_id: int) -> list[AgentToolCall]:
    result = await db.execute(
        select(AgentToolCall)
        .where(AgentToolCall.run_id == run_id)
        .order_by(AgentToolCall.id)
    )
    return list(result.scalars().all())


async def list_failures(db: AsyncSession, run_id: int) -> list[AgentFailureRecord]:
    result = await db.execute(
        select(AgentFailureRecord)
        .where(AgentFailureRecord.run_id == run_id)
        .order_by(AgentFailureRecord.id)
    )
    return list(result.scalars().all())


async def get_multi_agent_summary(
    db: AsyncSession,
    run_id: int,
    *,
    include_hidden_artifacts: bool = False,
) -> dict:
    from .workflow_summary_service import get_multi_agent_summary as aggregate_summary

    return await aggregate_summary(db, run_id, include_hidden_artifacts=include_hidden_artifacts)


async def ensure_workflow_owner_from_caller(
    db: AsyncSession,
    run_id: int,
    caller: str,
    *,
    allow_system: bool = True,
) -> AgentWorkflowRun:
    run = await _get_run(db, run_id)
    caller_id = _caller_user_id(caller)
    if caller_id is None:
        if allow_system and caller.startswith("system:"):
            return run
        raise PermissionDenied("Invalid caller for workflow owner check")
    _assert_run_visible(run, caller_id, False)
    return run
