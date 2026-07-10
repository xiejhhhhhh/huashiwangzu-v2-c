"""Seed and cleanup deterministic Agent workflow demo data."""

from __future__ import annotations

from typing import Any

from app.core.exceptions import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ApprovalQueue
from ..workflow_models import (
    AgentFailureRecord,
    AgentToolCall,
    AgentVerificationResult,
    AgentWorkflowArtifact,
    AgentWorkflowRun,
    AgentWorkflowStep,
)
from . import workflow_service as workflow_svc

DEFAULT_DEMO_MARKER = "agent-demo-workflow"


def _marker_meta(marker: str, scenario: str) -> dict[str, Any]:
    return {
        "demo_marker": marker,
        "workflow_demo": True,
        "scenario": scenario,
        "cleanup_hint": "POST /api/agent/workflows/demo-seed/cleanup",
    }


def _evidence_ref(marker: str, scenario: str, ref_id: str) -> dict[str, Any]:
    return {
        "type": "knowledge",
        "ref_key": "evidence_id",
        "ref_id": f"{marker}-{scenario}-{ref_id}",
        "source": "workflow-demo-seed",
        "source_module": "agent",
    }


async def _demo_run(
    db: AsyncSession,
    *,
    owner_id: int,
    creator_id: int,
    marker: str,
    scenario: str,
    title: str,
    intent: str,
) -> AgentWorkflowRun:
    return await workflow_svc.create_workflow(
        db,
        title=f"{marker}-{scenario}: {title}",
        intent=intent,
        source="demo_seed",
        owner_id=owner_id,
        creator_id=creator_id,
        extra_meta=_marker_meta(marker, scenario),
    )


async def seed_demo_workflows(
    db: AsyncSession,
    *,
    owner_id: int,
    creator_id: int,
    marker: str = DEFAULT_DEMO_MARKER,
    cleanup_existing: bool = True,
) -> dict[str, Any]:
    """Create repeatable workflow demo runs with realistic ledger rows."""
    if not marker.startswith("agent-demo-") and not marker.startswith("workflow-demo-"):
        raise ValidationError("demo marker must start with agent-demo- or workflow-demo-")
    if cleanup_existing:
        await cleanup_demo_workflows(db, marker=marker)

    created: list[dict[str, Any]] = []

    completed = await _demo_run(
        db,
        owner_id=owner_id,
        creator_id=creator_id,
        marker=marker,
        scenario="completed",
        title="knowledge research and report delivery",
        intent="Demo completed multi-agent workflow with references and artifacts.",
    )
    await workflow_svc.start_workflow(db, completed.id, progress_summary="子代理已完成知识检索与报告收口")
    research = await workflow_svc.create_step(
        db,
        run_id=completed.id,
        step_key="research-agent",
        title="Research agent",
        step_type="subagent",
        input_ref={"query": "workflow governance", "refs": [_evidence_ref(marker, "completed", "input")]},
        max_retries=1,
    )
    await workflow_svc.update_step_status(
        db,
        research.id,
        status="completed",
        summary="完成知识库检索并整理证据",
        output_ref={"chunk_id": f"{marker}-chunk-001", "refs": [_evidence_ref(marker, "completed", "chunk")]},
    )
    call = await workflow_svc.record_tool_call(
        db,
        run_id=completed.id,
        step_id=research.id,
        tool_name="knowledge__search",
        target_module="knowledge",
        action="search",
        arguments={"query": "Agent workflow governance seed"},
        caller=f"user:{owner_id}",
        status="running",
        agent_run_id=f"{marker}-research",
    )
    await workflow_svc.update_tool_call_status(
        db,
        call.id,
        status="completed",
        result_ref={"summary": "3 条证据命中", "refs": [_evidence_ref(marker, "completed", "tool")]},
    )
    await workflow_svc.create_artifact(
        db,
        run_id=completed.id,
        step_id=research.id,
        artifact_type="report",
        storage_kind="inline_summary",
        storage_ref={"artifact_id": f"{marker}-report-001", "refs": [_evidence_ref(marker, "completed", "report")]},
        lifecycle="published",
        summary="Agent workflow demo report",
        extra_meta=_marker_meta(marker, "completed"),
    )
    await workflow_svc.record_verification(
        db,
        run_id=completed.id,
        step_id=research.id,
        verification_type="probe",
        status="pass",
        command_or_capability="agent:get_multi_agent_summary",
        evidence_ref=_evidence_ref(marker, "completed", "probe"),
        summary="治理面板详情可回源",
        duration_ms=320,
    )
    completed = await workflow_svc.finalize_workflow(db, run_id=completed.id, developer_summary="Demo clean completed.")
    created.append({"id": completed.id, "status": completed.status, "scenario": "completed"})

    partial = await _demo_run(
        db,
        owner_id=owner_id,
        creator_id=creator_id,
        marker=marker,
        scenario="partial",
        title="release gate pass with debt",
        intent="Demo partial workflow with non-blocking verification debt.",
    )
    await workflow_svc.start_workflow(db, partial.id, progress_summary="主体完成，release gate 带债")
    repair = await workflow_svc.create_step(
        db,
        run_id=partial.id,
        step_key="repair-agent",
        title="Repair agent",
        step_type="subagent",
        input_ref={"refs": [_evidence_ref(marker, "partial", "input")]},
    )
    await workflow_svc.update_step_status(db, repair.id, status="completed", summary="完成主要修复")
    await workflow_svc.create_artifact(
        db,
        run_id=partial.id,
        step_id=repair.id,
        artifact_type="patch",
        storage_kind="inline_summary",
        storage_ref={"artifact_id": f"{marker}-patch-001"},
        summary="Demo patch with known debt",
        extra_meta=_marker_meta(marker, "partial"),
    )
    await workflow_svc.record_verification(
        db,
        run_id=partial.id,
        step_id=repair.id,
        verification_type="release_gate",
        status="debt",
        command_or_capability="release_gate --skip-ui --mode preflight",
        evidence_ref=_evidence_ref(marker, "partial", "release-gate"),
        summary="PASS_WITH_DEBT: UI skipped for demo preflight",
        duration_ms=980,
    )
    partial = await workflow_svc.finalize_workflow(db, run_id=partial.id, developer_summary="Demo completed with debt.")
    created.append({"id": partial.id, "status": partial.status, "scenario": "partial"})

    failed = await _demo_run(
        db,
        owner_id=owner_id,
        creator_id=creator_id,
        marker=marker,
        scenario="semantic-failed",
        title="semantic failure and retry sample",
        intent="Demo semantic failure with retry evidence.",
    )
    await workflow_svc.start_workflow(db, failed.id, progress_summary="语义验证失败，等待人工复核")
    writer = await workflow_svc.create_step(
        db,
        run_id=failed.id,
        step_key="writer-agent",
        title="Writer agent",
        step_type="subagent",
        max_retries=2,
    )
    tool = await workflow_svc.record_tool_call(
        db,
        run_id=failed.id,
        step_id=writer.id,
        tool_name="office-gen__write_ir",
        target_module="office-gen",
        action="write_ir",
        arguments={"content_type": "document", "marker": marker},
        caller=f"user:{owner_id}",
        status="running",
        side_effect_level="workspace_write",
        agent_run_id=f"{marker}-writer",
    )
    await workflow_svc.update_tool_call_status(
        db,
        tool.id,
        status="failed",
        result_ref={"summary": "Content IR semantic validation failed"},
        error_class="semantic_validation",
        error_signature="missing required evidence citation",
    )
    await workflow_svc.update_step_status(
        db,
        writer.id,
        status="failed",
        summary="生成文档缺少必要证据引用",
        error_class="semantic_validation",
        error_signature="missing required evidence citation",
    )
    await workflow_svc.record_failure(
        db,
        run_id=failed.id,
        step_id=writer.id,
        tool_call_id=tool.id,
        failure_type="semantic_failure",
        error_signature="missing required evidence citation",
        retryable=True,
        retry_count=1,
        next_action="retry",
        evidence_ref=_evidence_ref(marker, "semantic-failed", "invalid-ir"),
        handoff_note="语义失败：生成内容缺少证据引用，已触发一次重试样例。",
    )
    await workflow_svc.record_verification(
        db,
        run_id=failed.id,
        step_id=writer.id,
        verification_type="semantic_check",
        status="fail",
        command_or_capability="content:validate_ir",
        evidence_ref=_evidence_ref(marker, "semantic-failed", "verification"),
        summary="semantic failure: missing required evidence citation",
    )
    failed = await workflow_svc.finalize_workflow(db, run_id=failed.id, developer_summary="Demo semantic failure.")
    created.append({"id": failed.id, "status": failed.status, "scenario": "semantic_failed"})

    waiting = await _demo_run(
        db,
        owner_id=owner_id,
        creator_id=creator_id,
        marker=marker,
        scenario="needs-confirmation",
        title="dangerous tool approval sample",
        intent="Demo workflow paused on a sensitive tool approval.",
    )
    await workflow_svc.start_workflow(db, waiting.id, progress_summary="对外操作等待确认")
    approval_step = await workflow_svc.create_step(
        db,
        run_id=waiting.id,
        step_key="approval-agent",
        title="Approval gate",
        step_type="approval",
    )
    approval_call = await workflow_svc.record_tool_call(
        db,
        run_id=waiting.id,
        step_id=approval_step.id,
        tool_name="terminal-tools__exec",
        target_module="terminal-tools",
        action="exec",
        arguments={"command": "publish demo artifact", "marker": marker},
        caller=f"user:{owner_id}",
        side_effect_level="workspace_write",
        approval_policy="requires_admin",
        agent_run_id=f"{marker}-approval",
    )
    approval = await workflow_svc.request_approval(
        db,
        run_id=waiting.id,
        tool_call_id=approval_call.id,
        requested_by=creator_id,
        reason="Demo approval seed: publish candidate artifact",
        risk_level="medium",
        resume_target={"workflow_run_id": waiting.id, "tool_call_id": approval_call.id, "marker": marker},
    )
    created.append({"id": waiting.id, "status": "needs_confirmation", "scenario": "needs_confirmation", "approval_id": approval.id})

    return {"marker": marker, "created": created, "count": len(created)}


async def cleanup_demo_workflows(db: AsyncSession, *, marker: str = DEFAULT_DEMO_MARKER) -> dict[str, Any]:
    """Delete demo workflow rows created by this seed mechanism."""
    title_like = f"{marker}-%"
    result = await db.execute(
        select(AgentWorkflowRun.id).where(
            (AgentWorkflowRun.source == "demo_seed")
            & (
                AgentWorkflowRun.title.like(title_like)
                | AgentWorkflowRun.extra_meta["demo_marker"].as_string().in_([marker])
            )
        )
    )
    run_ids = [int(item) for item in result.scalars().all()]
    if not run_ids:
        return {"marker": marker, "deleted": 0, "run_ids": []}
    await db.execute(delete(ApprovalQueue).where(ApprovalQueue.workflow_run_id.in_(run_ids)))
    await db.execute(delete(AgentFailureRecord).where(AgentFailureRecord.run_id.in_(run_ids)))
    await db.execute(delete(AgentVerificationResult).where(AgentVerificationResult.run_id.in_(run_ids)))
    await db.execute(delete(AgentWorkflowArtifact).where(AgentWorkflowArtifact.run_id.in_(run_ids)))
    await db.execute(delete(AgentToolCall).where(AgentToolCall.run_id.in_(run_ids)))
    await db.execute(delete(AgentWorkflowStep).where(AgentWorkflowStep.run_id.in_(run_ids)))
    await db.execute(delete(AgentWorkflowRun).where(AgentWorkflowRun.id.in_(run_ids)))
    await db.commit()
    return {"marker": marker, "deleted": len(run_ids), "run_ids": run_ids}
