from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.exceptions import PermissionDenied, ValidationError
from app.database import AsyncSessionLocal
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.agent.backend.init_db import run_init
from modules.agent.backend.models import ApprovalQueue
from modules.agent.backend.services import workflow_seed_service as seed_svc
from modules.agent.backend.services import workflow_service as svc
from modules.agent.backend.workflow_models import (
    AgentFailureRecord,
    AgentToolCall,
    AgentVerificationResult,
    AgentWorkflowArtifact,
    AgentWorkflowRun,
    AgentWorkflowStep,
)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_workflow_schema() -> None:
    async with AsyncSessionLocal() as session:
        await run_init(session)


@pytest_asyncio.fixture()
async def db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def cleanup_runs(db: AsyncSession) -> AsyncIterator[list[int]]:
    run_ids: list[int] = []
    try:
        yield run_ids
    finally:
        if run_ids:
            await db.execute(delete(ApprovalQueue).where(ApprovalQueue.workflow_run_id.in_(run_ids)))
            await db.execute(delete(AgentFailureRecord).where(AgentFailureRecord.run_id.in_(run_ids)))
            await db.execute(delete(AgentVerificationResult).where(AgentVerificationResult.run_id.in_(run_ids)))
            await db.execute(delete(AgentWorkflowArtifact).where(AgentWorkflowArtifact.run_id.in_(run_ids)))
            await db.execute(delete(AgentToolCall).where(AgentToolCall.run_id.in_(run_ids)))
            await db.execute(delete(AgentWorkflowStep).where(AgentWorkflowStep.run_id.in_(run_ids)))
            await db.execute(delete(AgentWorkflowRun).where(AgentWorkflowRun.id.in_(run_ids)))
            await db.commit()


async def _new_run(db: AsyncSession, cleanup_runs: list[int], *, owner_id: int = 501) -> AgentWorkflowRun:
    run = await svc.create_workflow(
        db,
        title=f"workflow test {uuid4().hex}",
        intent="exercise workflow service state machine",
        source="manual",
        owner_id=owner_id,
        creator_id=owner_id,
        extra_meta={"test_marker": "workflow_service"},
    )
    cleanup_runs.append(run.id)
    return run


@pytest.mark.asyncio
async def test_create_start_step_tool_call_and_artifact_flow(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    run = await _new_run(db, cleanup_runs)

    assert run.status == "waiting"
    assert run.verification_status == "pending"
    assert run.progress_summary == "等待中"

    run = await svc.start_workflow(db, run.id, progress_summary="开始处理")
    assert run.status == "processing"
    assert run.started_at is not None

    step = await svc.create_step(
        db,
        run_id=run.id,
        step_key="plan",
        title="Plan task",
        step_type="plan",
        input_ref={"kind": "prompt"},
    )
    assert step.status == "pending"
    assert step.order_index == 1

    step = await svc.update_step_status(
        db,
        step.id,
        status="running",
        summary="planning",
    )
    assert step.status == "running"
    assert step.started_at is not None

    call = await svc.record_tool_call(
        db,
        run_id=run.id,
        step_id=step.id,
        tool_name="terminal-tools__exec",
        arguments={"command": "echo ok", "token": "secret"},
        caller="user:501",
        side_effect_level="workspace_write",
    )
    assert call.target_module == "terminal-tools"
    assert call.action == "exec"
    assert call.arguments_hash
    assert call.arguments_ref is not None
    assert call.arguments_ref["storage"] == "sanitized_summary"
    assert call.idempotency_key

    call = await svc.update_tool_call_status(
        db,
        call.id,
        status="completed",
        result_ref={"summary": "ok"},
    )
    assert call.status == "completed"
    assert call.finished_at is not None

    artifact = await svc.create_artifact(
        db,
        run_id=run.id,
        step_id=step.id,
        artifact_type="report",
        storage_kind="inline_summary",
        storage_ref={"summary": "result"},
        lifecycle="published",
        summary="workflow report",
    )
    assert artifact.lifecycle == "published"
    assert artifact.storage_kind == "inline_summary"

    refreshed = await svc.get_workflow(db, run.id, user_id=501)
    assert refreshed.artifact_summary["report"] == "workflow report"


@pytest.mark.asyncio
async def test_multi_agent_summary_empty_workflow_returns_empty_items(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    run = await _new_run(db, cleanup_runs)

    summary = await svc.get_multi_agent_summary(db, run.id)
    assert summary == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_demo_workflow_seed_creates_and_cleans_repeatable_samples(
    db: AsyncSession,
) -> None:
    marker = f"agent-demo-workflow-{uuid4().hex}"
    try:
        seeded = await seed_svc.seed_demo_workflows(
            db,
            owner_id=560,
            creator_id=560,
            marker=marker,
        )
        assert seeded["count"] == 4
        statuses = {item["scenario"]: item["status"] for item in seeded["created"]}
        assert statuses["completed"] == "completed"
        assert statuses["partial"] == "partial"
        assert statuses["semantic_failed"] == "failed"
        assert statuses["needs_confirmation"] == "needs_confirmation"

        runs = await svc.list_workflows(db, user_id=560, limit=20)
        demo_runs = [run for run in runs if run.title.startswith(marker)]
        assert len(demo_runs) == 4
        counts = await svc.get_workflow_rollup_counts(db, [run.id for run in demo_runs])
        assert any(item["artifact_count"] > 0 for item in counts.values())
        assert any(item["reference_count"] > 0 for item in counts.values())
        assert any(item["failure_count"] > 0 for item in counts.values())

        summary = await svc.get_workflow_governance_summary(db, owner_id=560)
        assert summary["total"] >= 4
        assert summary["failed"] >= 1
        assert summary["needs_confirmation"] >= 1
        assert any(item["failure_type"] == "semantic_failure" for item in summary["recent_errors"])
    finally:
        cleanup = await seed_svc.cleanup_demo_workflows(db, marker=marker)
        assert cleanup["deleted"] in {0, 4}
        remaining = list((await db.execute(
            select(AgentWorkflowRun).where(AgentWorkflowRun.title.like(f"{marker}-%"))
        )).scalars().all())
        assert remaining == []


@pytest.mark.asyncio
async def test_multi_agent_summary_aggregates_step_tool_artifact_failure_and_verification(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    run = await _new_run(db, cleanup_runs)
    await svc.start_workflow(db, run.id)

    completed_step = await svc.create_step(
        db,
        run_id=run.id,
        step_key="research-agent",
        title="Research agent",
        step_type="subagent",
        input_ref={"document_id": "doc-input-3"},
    )
    await svc.update_step_status(
        db,
        completed_step.id,
        status="completed",
        summary="Research completed",
        output_ref={"chunk_id": "chunk-output-9", "page": 4},
    )
    completed_call = await svc.record_tool_call(
        db,
        run_id=run.id,
        step_id=completed_step.id,
        tool_name="knowledge__search",
        arguments={"query": "contract"},
        status="running",
    )
    completed_call = await svc.update_tool_call_status(
        db,
        completed_call.id,
        status="completed",
        result_ref={"artifact_refs": [{"type": "file", "ref_key": "file_id", "ref_id": "1001"}]},
    )
    artifact = await svc.create_artifact(
        db,
        run_id=run.id,
        step_id=completed_step.id,
        artifact_type="subagent_result",
        storage_kind="inline_summary",
        storage_ref={"refs": [{"type": "document", "ref_key": "document_id", "ref_id": "doc-7", "package_id": "pkg-9"}]},
        summary="Research evidence",
    )
    verification = await svc.record_verification(
        db,
        run_id=run.id,
        step_id=completed_step.id,
        verification_type="manual_review",
        status="pass",
        summary="Evidence checked",
        evidence_ref={"source_file_id": 9901},
    )

    failed_step = await svc.create_step(
        db,
        run_id=run.id,
        step_key="writer-agent",
        title="Writer agent",
        step_type="subagent",
    )
    failed_call = await svc.record_tool_call(
        db,
        run_id=run.id,
        step_id=failed_step.id,
        tool_name="office-gen__write_ir",
        arguments={"title": "draft"},
        status="running",
    )
    await svc.update_tool_call_status(
        db,
        failed_call.id,
        status="failed",
        error_signature="IR validation failed",
    )
    failure = await svc.record_failure(
        db,
        run_id=run.id,
        step_id=failed_step.id,
        tool_call_id=failed_call.id,
        failure_type="tool_error",
        error_signature="write_ir rejected payload",
        next_action="retry",
        evidence_ref={"artifact_id": "failed-ir"},
        handoff_note="Need regenerate valid IR",
    )
    await svc.record_verification(
        db,
        run_id=run.id,
        step_id=failed_step.id,
        verification_type="schema_check",
        status="fail",
        summary="Schema failed",
    )

    summary = await svc.get_multi_agent_summary(db, run.id)
    assert summary["total"] == 2
    first, second = summary["items"]
    assert first["id"] == f"step:{completed_step.id}"
    assert first["status"] == "completed"
    assert first["completion_summary"] == "Research completed"
    assert first["artifact_ids"] == [artifact.id]
    assert first["tool_call_ids"] == [completed_call.id]
    assert first["verification_ids"] == [verification.id]
    assert {ref["ref_key"] for ref in first["reference_ids"]} >= {
        "file_id",
        "document_id",
        "source_file_id",
        "chunk_id",
        "page",
        "package_id",
    }
    file_ref = next(ref for ref in first["reference_ids"] if ref["ref_key"] == "file_id")
    assert file_ref["source_tool"] == "knowledge__search"
    assert file_ref["status"] == "completed"
    chunk_ref = next(ref for ref in first["reference_ids"] if ref["ref_key"] == "chunk_id")
    assert chunk_ref["source_tool"] == "research-agent"
    assert chunk_ref["status"] == "completed"
    assert first["next_action"] == "review_artifacts"

    assert second["id"] == f"step:{failed_step.id}"
    assert second["status"] == "failed"
    assert second["failure_reason"] == "Need regenerate valid IR"
    assert second["failure_ids"] == [failure.id]
    assert second["next_action"] == "retry"
    assert any(ref["ref_key"] == "artifact_id" and ref["ref_id"] == "failed-ir" for ref in second["reference_ids"])


@pytest.mark.asyncio
async def test_child_resources_must_belong_to_workflow_run(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    first = await _new_run(db, cleanup_runs, owner_id=521)
    second = await _new_run(db, cleanup_runs, owner_id=521)
    step = await svc.create_step(
        db,
        run_id=first.id,
        step_key="owned-step",
        title="Owned step",
        step_type="tool",
    )
    call = await svc.record_tool_call(
        db,
        run_id=first.id,
        step_id=step.id,
        tool_name="terminal-tools__exec",
        arguments={"command": "echo owned"},
        side_effect_level="workspace_write",
    )

    with pytest.raises(PermissionDenied):
        await svc.update_step_status(db, step.id, status="running", run_id=second.id)

    with pytest.raises(PermissionDenied):
        await svc.record_tool_call(
            db,
            run_id=second.id,
            step_id=step.id,
            tool_name="terminal-tools__exec",
            arguments={"command": "echo wrong"},
        )

    with pytest.raises(PermissionDenied):
        await svc.request_approval(
            db,
            run_id=second.id,
            tool_call_id=call.id,
            requested_by=521,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("verification_status", "summary", "expected_status", "expected_terminal", "expected_verification"),
    [
        ("pass", "all checks passed", "completed", "clean_completed", "pass"),
        ("debt", "non-blocking debt remains", "partial", "completed_with_debt", "debt"),
        ("fail", "required test failed", "failed", "failed_verified", "fail"),
    ],
)
async def test_finalize_workflow_uses_required_verification_result(
    db: AsyncSession,
    cleanup_runs: list[int],
    verification_status: str,
    summary: str,
    expected_status: str,
    expected_terminal: str,
    expected_verification: str,
) -> None:
    run = await _new_run(db, cleanup_runs)
    await svc.start_workflow(db, run.id)

    await svc.record_verification(
        db,
        run_id=run.id,
        verification_type="unit_test",
        status=verification_status,
        summary=summary,
        is_required_for_completion=True,
    )

    finalized = await svc.finalize_workflow(db, run_id=run.id, developer_summary="finalized by test")
    assert finalized.status == expected_status
    assert finalized.terminal_status == expected_terminal
    assert finalized.verification_status == expected_verification
    assert finalized.finished_at is not None
    assert finalized.developer_summary == "finalized by test"

    if verification_status == "fail":
        failures = await svc.list_failures(db, run.id)
        assert failures
        assert failures[0].failure_type == "test_failure"


@pytest.mark.asyncio
async def test_pass_with_debt_release_gate_cannot_clean_complete(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    run = await _new_run(db, cleanup_runs)
    await svc.start_workflow(db, run.id)

    await svc.record_verification(
        db,
        run_id=run.id,
        verification_type="release_gate",
        status="debt",
        summary="PASS_WITH_DEBT: skip-ui used",
        is_required_for_completion=True,
    )

    finalized = await svc.finalize_workflow(db, run_id=run.id)
    assert finalized.status == "partial"
    assert finalized.terminal_status == "completed_with_debt"
    assert finalized.verification_status == "debt"
    assert finalized.terminal_status != "clean_completed"


@pytest.mark.asyncio
async def test_finalize_requires_at_least_one_verification_result(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    run = await _new_run(db, cleanup_runs)
    await svc.start_workflow(db, run.id)

    with pytest.raises(ValidationError):
        await svc.finalize_workflow(db, run_id=run.id)


@pytest.mark.asyncio
async def test_approval_approve_resumes_workflow_and_original_tool_call(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    run = await _new_run(db, cleanup_runs)
    await svc.start_workflow(db, run.id)
    step = await svc.create_step(
        db,
        run_id=run.id,
        step_key="dangerous-tool",
        title="Dangerous tool",
        step_type="tool",
    )
    call = await svc.record_tool_call(
        db,
        run_id=run.id,
        step_id=step.id,
        tool_name="terminal-tools__exec",
        arguments={"command": "touch result.txt"},
        caller="user:501",
        side_effect_level="workspace_write",
        approval_policy="requires_user",
    )

    approval = await svc.request_approval(
        db,
        run_id=run.id,
        tool_call_id=call.id,
        requested_by=501,
        reason="workspace write",
    )
    assert approval.workflow_run_id == run.id
    assert approval.workflow_step_id == step.id
    assert approval.tool_call_id == call.id
    assert approval.payload_hash == call.arguments_hash
    assert approval.resume_target["tool_call_id"] == call.id

    paused_run = await svc.get_workflow(db, run.id, user_id=501)
    assert paused_run.status == "needs_confirmation"
    assert (await db.get(AgentToolCall, call.id)).status == "waiting_approval"

    result = await svc.resolve_approval(
        db,
        approval_id=approval.id,
        decision="approved",
        decided_by=900,
        payload_hash=call.arguments_hash,
    )
    assert result["status"] == "approved"

    resumed_run = await svc.get_workflow(db, run.id, user_id=501)
    resumed_call = await db.get(AgentToolCall, call.id)
    resumed_step = await db.get(AgentWorkflowStep, step.id)
    assert resumed_run.status == "processing"
    assert resumed_call.status == "planned"
    assert resumed_step.status == "running"


@pytest.mark.asyncio
async def test_approval_reject_marks_failed_and_records_failure(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    run = await _new_run(db, cleanup_runs)
    await svc.start_workflow(db, run.id)
    step = await svc.create_step(
        db,
        run_id=run.id,
        step_key="approval",
        title="Approval",
        step_type="approval",
    )
    call = await svc.record_tool_call(
        db,
        run_id=run.id,
        step_id=step.id,
        tool_name="terminal-tools__exec",
        arguments={"command": "rm unsafe"},
        caller="user:501",
        side_effect_level="dangerous",
        approval_policy="requires_admin",
    )
    approval = await svc.request_approval(
        db,
        run_id=run.id,
        tool_call_id=call.id,
        requested_by=501,
        reason="dangerous command",
    )

    result = await svc.resolve_approval(
        db,
        approval_id=approval.id,
        decision="rejected",
        decided_by=900,
        reason="unsafe command",
    )
    assert result["status"] == "rejected"

    failed_run = await svc.get_workflow(db, run.id, user_id=501)
    rejected_call = await db.get(AgentToolCall, call.id)
    failures = await svc.list_failures(db, run.id)
    assert failed_run.status == "failed"
    assert failed_run.terminal_status == "failed_verified"
    assert rejected_call.status == "rejected"
    assert failures
    assert failures[0].failure_type == "approval_rejected"


@pytest.mark.asyncio
async def test_owner_and_admin_visibility_filters(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    owner_run = await _new_run(db, cleanup_runs, owner_id=601)
    other_run = await _new_run(db, cleanup_runs, owner_id=602)

    owner_visible = await svc.list_workflows(db, user_id=601, is_admin=False, limit=20)
    owner_ids = {run.id for run in owner_visible}
    assert owner_run.id in owner_ids
    assert other_run.id not in owner_ids

    admin_visible = await svc.list_workflows(db, user_id=900, is_admin=True, limit=50)
    admin_ids = {run.id for run in admin_visible}
    assert {owner_run.id, other_run.id}.issubset(admin_ids)

    with pytest.raises(PermissionDenied):
        await svc.get_workflow(db, other_run.id, user_id=601, is_admin=False)

    assert (await svc.get_workflow(db, other_run.id, user_id=900, is_admin=True)).id == other_run.id
