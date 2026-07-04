"""Persistent Agent workflow ledger models.

These tables are owned by the agent module.  They intentionally do not extend
or depend on the framework workflow skeleton tables.
"""

from __future__ import annotations

from datetime import datetime

from app.models.base import Base, TimestampMixin
from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class AgentWorkflowRun(Base, TimestampMixin):
    """User-visible Agent task ledger root."""

    __tablename__ = "agent_workflow_runs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    intent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="waiting", index=True)
    terminal_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    current_step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    progress_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    developer_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    dirty_worktree_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    release_gate_verdict: Mapped[str | None] = mapped_column(String(64), nullable=True)
    queue_task_ids: Mapped[list] = mapped_column(JSON, default=list)
    artifact_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    extra_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentWorkflowStep(Base, TimestampMixin):
    """A durable stage inside an Agent workflow run."""

    __tablename__ = "agent_workflow_steps"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    step_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="agent")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_class: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_signature: Mapped[str | None] = mapped_column(String(256), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_meta: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentToolCall(Base, TimestampMixin):
    """Persisted tool/capability call plan and outcome."""

    __tablename__ = "agent_tool_calls"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_module: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str | None] = mapped_column(String(128), nullable=True)
    caller: Mapped[str | None] = mapped_column(String(128), nullable=True)
    arguments_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    side_effect_level: Mapped[str] = mapped_column(String(32), nullable=False, default="readonly")
    approval_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    result_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_signature: Mapped[str | None] = mapped_column(String(256), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_meta: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentWorkflowArtifact(Base, TimestampMixin):
    """Artifact metadata for workflow output and evidence."""

    __tablename__ = "agent_workflow_artifacts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_ref: Mapped[dict | str | None] = mapped_column(JSON, nullable=True)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_meta: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentVerificationResult(Base, TimestampMixin):
    """Verification evidence used to decide terminal workflow status."""

    __tablename__ = "agent_verification_results"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    verification_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    command_or_capability: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_required_for_completion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_meta: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentFailureRecord(Base, TimestampMixin):
    """Failure and recovery decision log."""

    __tablename__ = "agent_failure_records"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tool_call_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    failure_type: Mapped[str] = mapped_column(String(32), nullable=False)
    error_signature: Mapped[str | None] = mapped_column(String(256), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_action: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    evidence_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    handoff_note: Mapped[str | None] = mapped_column(Text, nullable=True)
