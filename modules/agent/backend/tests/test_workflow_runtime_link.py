from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from app.database import AsyncSessionLocal
from app.models.system import SystemTaskQueue
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from modules.agent.backend._utils import references_from_tool_events
from modules.agent.backend.handlers.tasks import _submit_slow_tool_task
from modules.agent.backend.init_db import run_init
from modules.agent.backend.models import AgentCheckpoint, ApprovalQueue
from modules.agent.backend.runtime.checkpointer import PostgresCheckpointSaver
from modules.agent.backend.runtime.task_sink import RuntimeTaskSink
from modules.agent.backend.runtime.workflow_link import WorkflowRuntimeLink
from modules.agent.backend.services import workflow_service as svc
from modules.agent.backend.services.action_policy import check_action_allowed
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
async def cleanup_runtime_records(db: AsyncSession) -> AsyncIterator[dict[str, list]]:
    records: dict[str, list] = {"run_ids": [], "checkpoint_ids": []}
    try:
        yield records
    finally:
        checkpoint_ids = records["checkpoint_ids"]
        if checkpoint_ids:
            await db.execute(delete(AgentCheckpoint).where(AgentCheckpoint.checkpoint_id.in_(checkpoint_ids)))
        run_ids = records["run_ids"]
        if run_ids:
            await db.execute(delete(ApprovalQueue).where(ApprovalQueue.workflow_run_id.in_(run_ids)))
            await db.execute(delete(AgentFailureRecord).where(AgentFailureRecord.run_id.in_(run_ids)))
            await db.execute(delete(AgentVerificationResult).where(AgentVerificationResult.run_id.in_(run_ids)))
            await db.execute(delete(AgentWorkflowArtifact).where(AgentWorkflowArtifact.run_id.in_(run_ids)))
            await db.execute(delete(AgentToolCall).where(AgentToolCall.run_id.in_(run_ids)))
            await db.execute(delete(AgentWorkflowStep).where(AgentWorkflowStep.run_id.in_(run_ids)))
            await db.execute(delete(AgentWorkflowRun).where(AgentWorkflowRun.id.in_(run_ids)))
        await db.commit()


def _sink(link: WorkflowRuntimeLink) -> RuntimeTaskSink:
    return RuntimeTaskSink(
        conversation_id=link.conversation_id,
        owner_id=link.owner_id,
        profile_key=link.profile_key,
        user_input=link.user_input,
        workflow_link=link,
    )


async def _linked_sink(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
    *,
    owner_id: int = 8801,
) -> RuntimeTaskSink:
    link = WorkflowRuntimeLink(
        conversation_id=-(uuid4().int >> 66),
        owner_id=owner_id,
        user_input="请执行一个需要工具的任务",
        profile_key="deepseek-v4-flash",
        user_message_id=123,
    )
    sink = _sink(link)
    await sink.ensure_workflow_started(db, reason="test")
    assert link.run_id is not None
    cleanup_runtime_records["run_ids"].append(link.run_id)
    return sink


@pytest.mark.asyncio
async def test_tool_call_auto_creates_workflow_ledger(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    link = WorkflowRuntimeLink(
        conversation_id=-(uuid4().int >> 66),
        owner_id=8802,
        user_input="请搜索知识库里的流程",
        user_message_id=456,
    )
    sink = _sink(link)

    call_id = await sink.workflow_record_tool_started(
        db,
        {"name": "knowledge__search", "tool_call_id": "call_ledger", "args": {"query": "流程"}},
    )
    assert call_id is not None
    assert link.run_id is not None
    cleanup_runtime_records["run_ids"].append(link.run_id)

    run = await svc.get_workflow(db, link.run_id, user_id=8802)
    call = await db.get(AgentToolCall, call_id)
    assert run.status == "processing"
    assert run.source == "agent_runtime"
    assert call is not None
    assert call.run_id == link.run_id
    assert call.step_id == link.step_id
    assert call.arguments_hash
    assert call.target_module == "knowledge"
    assert call.action == "search"


@pytest.mark.asyncio
async def test_side_effect_tool_gets_idempotency_key(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    sink = await _linked_sink(db, cleanup_runtime_records, owner_id=8803)

    call_id = await sink.workflow_record_tool_started(
        db,
        {"name": "terminal-tools__exec", "tool_call_id": "call_write", "args": {"command": "echo ok"}},
    )
    call = await db.get(AgentToolCall, call_id)
    assert call is not None
    assert call.side_effect_level != "readonly"
    assert call.idempotency_key


@pytest.mark.asyncio
async def test_policy_approval_links_workflow_payload_and_resume_target(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    sink = await _linked_sink(db, cleanup_runtime_records, owner_id=8804)
    call_id = await sink.workflow_record_tool_started(
        db,
        {"name": "im__send", "tool_call_id": "call_approval", "args": {"text": "hello"}},
    )
    call = await db.get(AgentToolCall, call_id)
    assert call is not None

    result = await check_action_allowed(
        db,
        "im__send",
        "workflow_runtime_test_agent",
        8804,
        conversation_id=sink.conversation_id,
        tool_args={"text": "hello"},
        workflow_run_id=sink.workflow_run_id,
        workflow_step_id=sink.workflow_step_id,
        workflow_tool_call_id=call.id,
        workflow_resume_target={
            "workflow_run_id": sink.workflow_run_id,
            "workflow_step_id": sink.workflow_step_id,
            "tool_call_id": call.id,
            "provider_tool_call_id": "call_approval",
        },
    )
    assert result["allowed"] is False
    assert result["action"] == "confirm"
    assert result["payload_hash"] == call.arguments_hash

    approval = await db.get(ApprovalQueue, result["approval_id"])
    assert approval is not None
    assert approval.workflow_run_id == sink.workflow_run_id
    assert approval.workflow_step_id == sink.workflow_step_id
    assert approval.tool_call_id == call.id
    assert approval.payload_hash == call.arguments_hash
    assert approval.resume_target["provider_tool_call_id"] == "call_approval"


@pytest.mark.asyncio
async def test_checkpoint_persists_workflow_resume_context(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    sink = await _linked_sink(db, cleanup_runtime_records, owner_id=8805)
    checkpoint_id = f"workflow-runtime-{uuid4().hex}"
    cleanup_runtime_records["checkpoint_ids"].append(checkpoint_id)
    saver = PostgresCheckpointSaver()

    await saver.put(
        db,
        conversation_id=sink.conversation_id,
        owner_id=sink.owner_id,
        checkpoint_id=checkpoint_id,
        step=3,
        channel_values={"messages": [], "workflow": sink.workflow_link.to_channel_values()},
        workflow_run_id=sink.workflow_run_id,
        workflow_step_id=sink.workflow_step_id,
        agent_run_id=sink.agent_run_id,
        checkpoint_type="tool_round",
        resume_cursor={"round": 3, "llm_to_ledger_call": {"abc": 12}},
    )
    restored = await saver.get_tuple(db, sink.conversation_id, checkpoint_id)
    assert restored is not None
    assert restored["workflow_run_id"] == sink.workflow_run_id
    assert restored["workflow_step_id"] == sink.workflow_step_id
    assert restored["agent_run_id"] == sink.agent_run_id
    assert restored["resume_cursor"]["llm_to_ledger_call"]["abc"] == 12
    restored_link = WorkflowRuntimeLink.from_channel_values(
        conversation_id=sink.conversation_id,
        owner_id=sink.owner_id,
        user_input=sink.user_input,
        profile_key=sink.profile_key,
        channel_values=restored["channel_values"],
    )
    assert restored_link.run_id == sink.workflow_run_id
    assert restored_link.step_id == sink.workflow_step_id


@pytest.mark.asyncio
async def test_slow_tool_task_carries_workflow_resume_context(db: AsyncSession) -> None:
    task_id = await _submit_slow_tool_task(
        conversation_id=-8809,
        user_id=1,
        tool_name="knowledge__search",
        skill_args={"query": "workflow"},
        caller="user:1",
        caller_role="viewer",
        workflow_run_id=101,
        workflow_step_id=202,
        workflow_tool_call_id=303,
        idempotency_key="idem-303",
    )
    try:
        task = await db.get(SystemTaskQueue, task_id)
        assert task is not None
        params = json.loads(task.parameters)
        assert params["workflow_run_id"] == 101
        assert params["workflow_step_id"] == 202
        assert params["tool_call_id"] == 303
        assert params["idempotency_key"] == "idem-303"
    finally:
        await db.execute(delete(SystemTaskQueue).where(SystemTaskQueue.id == task_id))
        await db.commit()


@pytest.mark.asyncio
async def test_subagent_result_records_step_artifact_and_failure(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    sink = await _linked_sink(db, cleanup_runtime_records, owner_id=8806)
    call_id = await sink.workflow_record_tool_started(
        db,
        {
            "name": "agent__spawn_subagent",
            "tool_call_id": "call_subagent",
            "args": {"tasks": [{"description": "read"}, {"description": "fail"}]},
        },
    )
    await sink.workflow_mark_tool_result(
        db,
        {
            "type": "tool_result",
            "name": "agent__spawn_subagent",
            "tool_call_id": "call_subagent",
            "result": {
                "results": [
                    {"task": "read", "status": "completed", "conclusion": "done"},
                    {"task": "fail", "status": "error", "error": "subagent failed"},
                ],
            },
        },
    )

    steps = await svc.list_steps(db, sink.workflow_run_id)
    subagent_steps = [step for step in steps if step.type == "subagent"]
    assert len(subagent_steps) == 2
    assert {step.status for step in subagent_steps} == {"completed", "failed"}

    artifacts = await svc.list_artifacts(db, sink.workflow_run_id)
    assert any(item.artifact_type == "subagent_result" and item.summary == "done" for item in artifacts)

    failures = await svc.list_failures(db, sink.workflow_run_id)
    assert any(item.tool_call_id == call_id and item.failure_type == "tool_error" for item in failures)


@pytest.mark.asyncio
async def test_skill_use_subagent_result_records_workflow_outputs(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    sink = await _linked_sink(db, cleanup_runtime_records, owner_id=8810)
    await sink.workflow_record_tool_started(
        db,
        {
            "name": "skill_use",
            "tool_call_id": "call_skill_subagent",
            "args": {
                "name": "agent__spawn_subagent",
                "args": {"tasks": [{"description": "inspect"}]},
            },
        },
    )

    await sink.workflow_mark_tool_result(
        db,
        {
            "type": "tool_result",
            "name": "skill_use",
            "effective_tool_name": "agent__spawn_subagent",
            "tool_call_id": "call_skill_subagent",
            "result": {
                "success": True,
                "data": {
                    "results": [
                        {
                            "task": "inspect",
                            "status": "completed",
                            "conclusion": "subagent inspected",
                        },
                    ],
                },
            },
        },
    )

    steps = await svc.list_steps(db, sink.workflow_run_id)
    assert any(step.type == "subagent" and step.status == "completed" for step in steps)
    artifacts = await svc.list_artifacts(db, sink.workflow_run_id)
    assert any(
        item.artifact_type == "subagent_result"
        and item.summary == "subagent inspected"
        for item in artifacts
    )


@pytest.mark.asyncio
async def test_tool_result_reference_ids_are_preserved_in_message_refs_and_workflow_artifacts(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    sink = await _linked_sink(db, cleanup_runtime_records, owner_id=8812)
    call_id = await sink.workflow_record_tool_started(
        db,
        {
            "name": "office-gen__write_ir",
            "tool_call_id": "call_artifact_refs",
            "args": {"title": "引用测试"},
        },
    )
    result_event = {
        "type": "tool_result",
        "name": "office-gen__write_ir",
        "tool_call_id": "call_artifact_refs",
        "result": {
            "success": True,
            "data": {
                "file_id": 71001,
                "package_id": "pkg-71001",
                "document_id": 81001,
                "chunks": [{"chunk_id": "chunk-1", "page": 3}],
                "source_file_id": 61001,
            },
        },
    }

    await sink.workflow_mark_tool_result(db, result_event)
    call = await db.get(AgentToolCall, call_id)
    assert call is not None
    assert call.status == "completed"
    assert any(ref["ref_key"] == "file_id" and ref["ref_id"] == "71001" for ref in call.result_ref["artifact_refs"])

    artifacts = await svc.list_artifacts(db, sink.workflow_run_id)
    tool_refs = [item for item in artifacts if item.artifact_type == "tool_reference"]
    assert tool_refs
    refs = tool_refs[-1].storage_ref["refs"]
    assert {ref["ref_key"] for ref in refs} >= {"file_id", "package_id", "document_id", "chunk_id", "page", "source_file_id"}

    message_refs = references_from_tool_events([result_event])
    assert any(ref["ref_key"] == "package_id" and ref["ref_id"] == "pkg-71001" for ref in message_refs)


@pytest.mark.asyncio
async def test_runtime_failure_without_existing_workflow_creates_failed_ledger(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    link = WorkflowRuntimeLink(
        conversation_id=-(uuid4().int >> 66),
        owner_id=8813,
        user_input="触发模型错误",
        profile_key="deepseek-v4-flash",
        user_message_id=987,
    )
    sink = _sink(link)

    await sink.workflow_record_runtime_failure(
        db,
        error_type="model_error",
        error_message="provider returned error payload",
    )
    assert link.run_id is not None
    cleanup_runtime_records["run_ids"].append(link.run_id)

    run = await svc.get_workflow(db, link.run_id, user_id=8813)
    assert run.status == "failed"
    assert run.verification_status == "fail"

    failures = await svc.list_failures(db, link.run_id)
    assert any(item.failure_type == "tool_error" for item in failures)
    verifications = await svc.list_verifications(db, link.run_id)
    assert any(item.verification_type == "runtime_exception" and item.status == "fail" for item in verifications)


@pytest.mark.asyncio
async def test_turn_completion_keeps_paused_step_when_approval_pending(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    sink = await _linked_sink(db, cleanup_runtime_records, owner_id=8811)
    call_id = await sink.workflow_record_tool_started(
        db,
        {
            "name": "terminal-tools__exec",
            "tool_call_id": "call_pending_approval",
            "args": {"command": "touch reviewed"},
        },
    )
    assert call_id is not None
    approval = await svc.request_approval(
        db,
        run_id=sink.workflow_run_id,
        tool_call_id=call_id,
        requested_by=8811,
        reason="needs confirmation",
    )

    await sink.workflow_complete_turn(
        db,
        message_id=1001,
        tool_events=[
            {
                "type": "tool_result",
                "name": "terminal-tools__exec",
                "tool_call_id": "call_pending_approval",
                "result": {"approval_required": True, "approval_id": approval.id},
            },
        ],
        completion_evidence=[],
        usage={"total_tokens": 1},
    )

    run = await svc.get_workflow(db, sink.workflow_run_id, user_id=8811)
    step = await db.get(AgentWorkflowStep, sink.workflow_step_id)
    assert run.status == "needs_confirmation"
    assert step is not None
    assert step.status == "paused"

    await svc.resolve_approval(
        db,
        approval_id=approval.id,
        decision="approved",
        decided_by=900,
        payload_hash=(await db.get(AgentToolCall, call_id)).arguments_hash,
    )
    resumed_step = await db.get(AgentWorkflowStep, sink.workflow_step_id)
    assert resumed_step is not None
    assert resumed_step.status == "running"


@pytest.mark.asyncio
async def test_turn_completion_records_verification_and_prevents_clean_debt(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    sink = await _linked_sink(db, cleanup_runtime_records, owner_id=8807)
    await sink.workflow_record_tool_started(
        db,
        {"name": "knowledge__search", "tool_call_id": "call_result", "args": {"query": "x"}},
    )
    await sink.workflow_mark_tool_result(
        db,
        {
            "type": "tool_result",
            "name": "knowledge__search",
            "tool_call_id": "call_result",
            "result": {"success": True, "data": {"items": []}},
        },
    )
    await sink.workflow_complete_turn(
        db,
        message_id=999,
        tool_events=[
            {"type": "tool_call", "name": "knowledge__search", "tool_call_id": "call_result", "arguments": {"query": "x"}},
            {"type": "tool_result", "name": "knowledge__search", "tool_call_id": "call_result", "result": {"success": True}},
        ],
        completion_evidence=[],
        usage={"total_tokens": 3},
    )
    run = await svc.get_workflow(db, sink.workflow_run_id, user_id=8807)
    assert run.status == "completed"
    assert run.terminal_status == "clean_completed"

    debt = await svc.create_workflow(
        db,
        title=f"runtime debt {uuid4().hex}",
        intent="debt mapping",
        source="agent_runtime",
        owner_id=8807,
        creator_id=8807,
    )
    cleanup_runtime_records["run_ids"].append(debt.id)
    await svc.start_workflow(db, debt.id)
    await svc.record_verification(
        db,
        run_id=debt.id,
        verification_type="release_gate",
        status="debt",
        summary="PASS_WITH_DEBT: runtime link test",
        is_required_for_completion=True,
    )
    finalized = await svc.finalize_workflow(db, run_id=debt.id)
    assert finalized.status == "partial"
    assert finalized.terminal_status == "completed_with_debt"


@pytest.mark.asyncio
async def test_rejected_workflow_approval_cannot_complete(
    db: AsyncSession,
    cleanup_runtime_records: dict[str, list],
) -> None:
    sink = await _linked_sink(db, cleanup_runtime_records, owner_id=8808)
    call_id = await sink.workflow_record_tool_started(
        db,
        {"name": "terminal-tools__exec", "tool_call_id": "call_reject", "args": {"command": "rm unsafe"}},
    )
    call = await db.get(AgentToolCall, call_id)
    approval = await svc.request_approval(
        db,
        run_id=sink.workflow_run_id,
        tool_call_id=call.id,
        requested_by=8808,
        reason="unsafe",
    )
    result = await svc.resolve_approval(
        db,
        approval_id=approval.id,
        decision="rejected",
        decided_by=1,
        reason="unsafe",
    )
    assert result["status"] == "rejected"
    run = await svc.get_workflow(db, sink.workflow_run_id, user_id=8808)
    assert run.status == "failed"
    assert run.terminal_status == "failed_verified"
    assert run.terminal_status != "clean_completed"
