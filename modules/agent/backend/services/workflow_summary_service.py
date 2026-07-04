"""Read-only multi-agent workflow summary aggregation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .._utils import artifact_refs_from_value
from ..workflow_models import (
    AgentFailureRecord,
    AgentToolCall,
    AgentVerificationResult,
    AgentWorkflowArtifact,
    AgentWorkflowRun,
    AgentWorkflowStep,
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _is_ref_dict(value: dict[str, Any]) -> bool:
    return bool(value.get("ref_id")) and bool(value.get("ref_key") or value.get("type") or value.get("source"))


def _reference_ids_from_value(
    value: Any,
    *,
    source_tool: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []

    def add_context(ref: dict[str, Any]) -> dict[str, Any]:
        item = dict(ref)
        if source_tool and not item.get("source_tool"):
            item["source_tool"] = source_tool
        if status and not item.get("status"):
            item["status"] = status
        return item

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if _is_ref_dict(node):
                refs.append(add_context(node))
            for child in node.values():
                walk(child)
        elif isinstance(node, list | tuple):
            for child in node:
                walk(child)

    walk(value)
    refs.extend(add_context(ref) for ref in artifact_refs_from_value(value))
    return _dedupe_refs(refs)


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for ref in refs:
        key = ":".join(str(ref.get(part) or "") for part in ("type", "ref_key", "source", "ref_id", "title"))
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _latest_failure_reason(
    step: AgentWorkflowStep | None,
    calls: list[AgentToolCall],
    failures: list[AgentFailureRecord],
    verifications: list[AgentVerificationResult],
) -> str | None:
    if failures:
        item = failures[-1]
        return item.handoff_note or item.error_signature or item.failure_type
    if step and (step.error_signature or step.error_class):
        return step.error_signature or step.error_class
    for call in reversed(calls):
        if call.status in {"failed", "blocked", "rejected", "interrupted"}:
            return call.error_signature or call.error_class or call.status
    for item in reversed(verifications):
        if item.status == "fail":
            return item.summary or item.verification_type
    return None


def _completion_summary(
    step: AgentWorkflowStep | None,
    calls: list[AgentToolCall],
    artifacts: list[AgentWorkflowArtifact],
    verifications: list[AgentVerificationResult],
) -> str | None:
    if step and step.summary:
        return step.summary
    for artifact in reversed(artifacts):
        if artifact.summary:
            return artifact.summary
    for item in reversed(verifications):
        if item.status in {"pass", "debt"} and item.summary:
            return item.summary
    for call in reversed(calls):
        ref = call.result_ref or {}
        if isinstance(ref, dict) and isinstance(ref.get("summary"), str):
            return ref["summary"]
    return None


def _summary_status(
    step: AgentWorkflowStep | None,
    calls: list[AgentToolCall],
    failures: list[AgentFailureRecord],
    verifications: list[AgentVerificationResult],
) -> str:
    if any(item.status == "fail" for item in verifications):
        return "failed"
    if any(call.status in {"blocked", "waiting_approval"} for call in calls):
        return "blocked"
    if any(call.status in {"failed", "rejected", "interrupted"} for call in calls) or failures:
        return "failed"
    if step and step.status in {"paused", "cancelled"}:
        return "blocked"
    if step and step.status in {"completed", "skipped"}:
        return "completed"
    if step and step.status == "failed":
        return "failed"
    if any(call.status == "running" for call in calls):
        return "running"
    if calls and all(call.status == "completed" for call in calls):
        return "completed"
    return "running"


def _next_action(status: str, failures: list[AgentFailureRecord], has_refs: bool) -> str:
    if failures:
        return failures[-1].next_action
    if status in {"failed", "blocked"}:
        return "manual"
    if status in {"running", "pending"}:
        return "continue"
    if status == "completed" and has_refs:
        return "review_artifacts"
    return "none"


def _summary_item(
    *,
    key: str,
    run_id: int,
    step: AgentWorkflowStep | None,
    calls: list[AgentToolCall],
    artifacts: list[AgentWorkflowArtifact],
    failures: list[AgentFailureRecord],
    verifications: list[AgentVerificationResult],
) -> dict[str, Any]:
    refs: list[dict[str, Any]] = []
    if step:
        step_source = step.step_key or step.title or f"step:{step.id}"
        refs.extend(_reference_ids_from_value(step.input_ref, source_tool=step_source, status=step.status))
        refs.extend(_reference_ids_from_value(step.output_ref, source_tool=step_source, status=step.status))
    for call in calls:
        refs.extend(_reference_ids_from_value(call.result_ref, source_tool=call.tool_name, status=call.status))
    for artifact in artifacts:
        artifact_source = artifact.artifact_type or artifact.storage_kind
        refs.extend(_reference_ids_from_value(artifact.storage_ref, source_tool=artifact_source, status=artifact.lifecycle))
    for item in [*failures, *verifications]:
        if isinstance(item, AgentFailureRecord):
            refs.extend(_reference_ids_from_value(
                item.evidence_ref,
                source_tool=item.failure_type,
                status=item.next_action,
            ))
        else:
            refs.extend(_reference_ids_from_value(
                item.evidence_ref,
                source_tool=item.verification_type,
                status=item.status,
            ))
    refs = _dedupe_refs(refs)
    status = _summary_status(step, calls, failures, verifications)
    return {
        "id": key,
        "run_id": run_id,
        "step_id": step.id if step else None,
        "step_key": step.step_key if step else None,
        "title": step.title if step else (calls[0].tool_name if calls else "Workflow run"),
        "type": step.type if step else ("tool_call" if calls else "run"),
        "status": status,
        "completion_summary": _completion_summary(step, calls, artifacts, verifications),
        "failure_reason": _latest_failure_reason(step, calls, failures, verifications),
        "reference_ids": refs,
        "artifact_ids": [item.id for item in artifacts],
        "tool_call_ids": [item.id for item in calls],
        "verification_ids": [item.id for item in verifications],
        "failure_ids": [item.id for item in failures],
        "next_action": _next_action(status, failures, bool(refs or artifacts)),
        "updated_at": _iso(step.updated_at if step else (calls[-1].updated_at if calls else None)),
    }


async def get_multi_agent_summary(
    db: AsyncSession,
    run_id: int,
    *,
    include_hidden_artifacts: bool = False,
) -> dict[str, Any]:
    steps = list((await db.execute(
        select(AgentWorkflowStep)
        .where(AgentWorkflowStep.run_id == run_id)
        .order_by(AgentWorkflowStep.order_index, AgentWorkflowStep.id)
    )).scalars().all())
    calls = list((await db.execute(
        select(AgentToolCall).where(AgentToolCall.run_id == run_id).order_by(AgentToolCall.id)
    )).scalars().all())
    artifacts_stmt = select(AgentWorkflowArtifact).where(AgentWorkflowArtifact.run_id == run_id)
    if not include_hidden_artifacts:
        artifacts_stmt = artifacts_stmt.where(AgentWorkflowArtifact.visibility.in_(("user", "developer")))
    artifacts = list((await db.execute(artifacts_stmt.order_by(AgentWorkflowArtifact.id))).scalars().all())
    failures = list((await db.execute(
        select(AgentFailureRecord).where(AgentFailureRecord.run_id == run_id).order_by(AgentFailureRecord.id)
    )).scalars().all())
    verifications = list((await db.execute(
        select(AgentVerificationResult).where(AgentVerificationResult.run_id == run_id).order_by(AgentVerificationResult.id)
    )).scalars().all())

    calls_by_step: dict[int | None, list[AgentToolCall]] = defaultdict(list)
    artifacts_by_step: dict[int | None, list[AgentWorkflowArtifact]] = defaultdict(list)
    failures_by_step: dict[int | None, list[AgentFailureRecord]] = defaultdict(list)
    verifications_by_step: dict[int | None, list[AgentVerificationResult]] = defaultdict(list)
    for item in calls:
        calls_by_step[item.step_id].append(item)
    for item in artifacts:
        artifacts_by_step[item.step_id].append(item)
    for item in failures:
        failures_by_step[item.step_id].append(item)
    for item in verifications:
        verifications_by_step[item.step_id].append(item)

    items = [
        _summary_item(
            key=f"step:{step.id}",
            run_id=run_id,
            step=step,
            calls=calls_by_step.get(step.id, []),
            artifacts=artifacts_by_step.get(step.id, []),
            failures=failures_by_step.get(step.id, []),
            verifications=verifications_by_step.get(step.id, []),
        )
        for step in steps
    ]
    for call in calls_by_step.get(None, []):
        items.append(_summary_item(
            key=f"tool_call:{call.id}",
            run_id=run_id,
            step=None,
            calls=[call],
            artifacts=[],
            failures=[item for item in failures_by_step.get(None, []) if item.tool_call_id == call.id],
            verifications=[],
        ))
    run_level_artifacts = artifacts_by_step.get(None, [])
    run_level_failures = [item for item in failures_by_step.get(None, []) if item.tool_call_id is None]
    run_level_verifications = verifications_by_step.get(None, [])
    if run_level_artifacts or run_level_failures or run_level_verifications:
        items.append(_summary_item(
            key=f"run:{run_id}",
            run_id=run_id,
            step=None,
            calls=[],
            artifacts=run_level_artifacts,
            failures=run_level_failures,
            verifications=run_level_verifications,
        ))
    return {"items": items, "total": len(items)}


async def get_workflow_rollup_counts(
    db: AsyncSession,
    run_ids: list[int],
    *,
    include_hidden_artifacts: bool = False,
) -> dict[int, dict[str, int]]:
    """Aggregate list-card counts without loading full workflow details."""
    if not run_ids:
        return {}
    unique_ids = sorted(set(int(run_id) for run_id in run_ids))
    counts = {
        run_id: {
            "step_count": 0,
            "tool_call_count": 0,
            "failure_count": 0,
            "artifact_count": 0,
            "verification_count": 0,
            "reference_count": 0,
        }
        for run_id in unique_ids
    }

    steps = list((await db.execute(
        select(AgentWorkflowStep).where(AgentWorkflowStep.run_id.in_(unique_ids))
    )).scalars().all())
    calls = list((await db.execute(
        select(AgentToolCall).where(AgentToolCall.run_id.in_(unique_ids))
    )).scalars().all())
    artifacts_stmt = select(AgentWorkflowArtifact).where(AgentWorkflowArtifact.run_id.in_(unique_ids))
    if not include_hidden_artifacts:
        artifacts_stmt = artifacts_stmt.where(AgentWorkflowArtifact.visibility.in_(("user", "developer")))
    artifacts = list((await db.execute(artifacts_stmt)).scalars().all())
    failures = list((await db.execute(
        select(AgentFailureRecord).where(AgentFailureRecord.run_id.in_(unique_ids))
    )).scalars().all())
    verifications = list((await db.execute(
        select(AgentVerificationResult).where(AgentVerificationResult.run_id.in_(unique_ids))
    )).scalars().all())

    for step in steps:
        counts[step.run_id]["step_count"] += 1
        counts[step.run_id]["reference_count"] += len(_reference_ids_from_value(step.input_ref))
        counts[step.run_id]["reference_count"] += len(_reference_ids_from_value(step.output_ref))
    for call in calls:
        counts[call.run_id]["tool_call_count"] += 1
        counts[call.run_id]["reference_count"] += len(_reference_ids_from_value(call.result_ref))
    for artifact in artifacts:
        counts[artifact.run_id]["artifact_count"] += 1
        counts[artifact.run_id]["reference_count"] += len(_reference_ids_from_value(artifact.storage_ref))
    for failure in failures:
        counts[failure.run_id]["failure_count"] += 1
        counts[failure.run_id]["reference_count"] += len(_reference_ids_from_value(failure.evidence_ref))
    for verification in verifications:
        counts[verification.run_id]["verification_count"] += 1
        counts[verification.run_id]["reference_count"] += len(_reference_ids_from_value(verification.evidence_ref))

    return counts


async def get_workflow_governance_summary(
    db: AsyncSession,
    *,
    owner_id: int,
    is_admin: bool = False,
    limit_recent_errors: int = 5,
) -> dict[str, Any]:
    """Aggregate lightweight governance metrics for visible workflows."""
    stmt = select(AgentWorkflowRun)
    if not is_admin:
        stmt = stmt.where(AgentWorkflowRun.owner_id == owner_id)
    runs = list((await db.execute(stmt.order_by(AgentWorkflowRun.id.desc()))).scalars().all())
    run_ids = [run.id for run in runs]
    counts = await get_workflow_rollup_counts(db, run_ids, include_hidden_artifacts=is_admin)
    total_duration_ms = 0
    duration_count = 0
    for run in runs:
        if run.started_at and run.finished_at:
            total_duration_ms += max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))
            duration_count += 1

    failures: list[AgentFailureRecord] = []
    if run_ids:
        failures = list((await db.execute(
            select(AgentFailureRecord)
            .where(AgentFailureRecord.run_id.in_(run_ids))
            .order_by(AgentFailureRecord.id.desc())
            .limit(max(1, min(limit_recent_errors, 20)))
        )).scalars().all())

    return {
        "total": len(runs),
        "failed": sum(1 for run in runs if run.status == "failed"),
        "partial": sum(1 for run in runs if run.status == "partial"),
        "completed": sum(1 for run in runs if run.status == "completed"),
        "needs_confirmation": sum(1 for run in runs if run.status == "needs_confirmation"),
        "with_artifacts": sum(1 for run_id in run_ids if counts.get(run_id, {}).get("artifact_count", 0) > 0),
        "with_references": sum(1 for run_id in run_ids if counts.get(run_id, {}).get("reference_count", 0) > 0),
        "average_duration_ms": int(total_duration_ms / duration_count) if duration_count else 0,
        "recent_errors": [
            {
                "run_id": item.run_id,
                "step_id": item.step_id,
                "tool_call_id": item.tool_call_id,
                "failure_type": item.failure_type,
                "reason": item.handoff_note or item.error_signature or item.failure_type,
                "retryable": item.retryable,
                "retry_count": item.retry_count,
                "next_action": item.next_action,
                "created_at": _iso(item.created_at),
            }
            for item in failures
        ],
    }
