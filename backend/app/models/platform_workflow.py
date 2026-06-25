"""Platform Workflow Run Ledger — minimum skeleton tables.

These tables track the execution lifecycle of platform workflows.
They are deliberately kept minimal — the goal is to establish
stable table names, column contracts, and foreign-key scaffolding
so that future workflow expansion (Dify/Coze-style orchestration,
langgraph-style state machines) can target real DB rows without
a migration rewrite.

Table naming follows the ``framework_workflow_{domain}`` convention.
All tables inherit TimestampMixin for created_at / updated_at.
"""
from datetime import datetime
from sqlalchemy import Integer, BigInteger, String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


# SQLAlchemy reserves ``metadata`` as a class-level attribute on DeclarativeBase,
# so we use ``extra_meta`` as the column name for arbitrary key-value payloads.


class WorkflowDefinition(Base, TimestampMixin):
    """A workflow template — defines the node graph and binding topology.

    ``nodes`` and ``edges`` are stored as JSON so that the graph shape
    can evolve without schema migrations.  Each node carries a node_type
    and optional resource bindings.  ``manifest`` holds version info,
    tags, and other metadata the orchestrator needs at dispatch time.
    """
    __tablename__ = "framework_workflow_definitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, comment="Workflow display name")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("framework_user_accounts.id"),
        nullable=False, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft",
        comment="draft | published | archived",
    )

    # Graph topology (JSON — no separate nodes/edges tables yet)
    nodes: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="List of node definitions: [{id, type, label, config, input_bindings, output_bindings}]",
    )
    edges: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="List of edge definitions: [{source_node_id, target_node_id, condition}]",
    )

    # Versioning and manifest
    version: Mapped[str] = mapped_column(String(32), default="1.0", comment="Semver for this definition")
    manifest: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Extended metadata: tags, category, timeout, retry_policy, etc.",
    )


class WorkflowRunRecord(Base, TimestampMixin):
    """A single execution of a workflow definition.

    Tracks the entire run lifecycle from queued through completed or
    failed.  ``trace`` carries a correlation id that spans all steps,
    events, and logs for this run.  ``context`` holds the initial
    input parameters as a JSON blob.
    """
    __tablename__ = "framework_workflow_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("framework_workflow_definitions.id"),
        nullable=False, index=True,
    )
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("framework_user_accounts.id"),
        nullable=False, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
        comment="pending | running | completed | failed | cancelled",
    )

    # Timeline
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Trace and context
    trace: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True,
        comment="Correlation id linking steps, events, and logs",
    )
    context: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Run-level input parameters (the initial resource refs)",
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Final error message if failed")

    # Extensibility (``meta`` not ``metadata`` — SQLAlchemy reserves the latter)
    extra_meta: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Arbitrary key-value metadata for future expansion",
    )


class WorkflowStepRecord(Base, TimestampMixin):
    """A single step within a workflow run.

    Each step maps to one node in the definition graph.  ``input_ref``
    and ``output_ref`` are ResourceRef pointers (id + resource_type)
    that link to the actual data consumed or produced by this step,
    without forcing a foreign key into a specific resource table.

    ``attempt`` tracks retries; ``error`` captures the last failure
    detail so the orchestrator can decide whether to retry or fail.
    """
    __tablename__ = "framework_workflow_step_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("framework_workflow_runs.id"),
        nullable=False, index=True,
    )
    node_id: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="Matches a node id in the definition's nodes list",
    )
    node_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="task",
        comment="task | decision | fork | join | sub_workflow",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
        comment="pending | running | completed | failed | skipped",
    )

    # Input / output as resource references
    input_ref: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON: [{resource_type, id, label}] — resources consumed by this step",
    )
    output_ref: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON: [{resource_type, id, label}] — resources produced by this step",
    )

    # Timeline
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Retry and error
    attempt: Mapped[int] = mapped_column(Integer, default=1, comment="Current retry attempt number")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Last error detail")

    # Extensibility
    extra_meta: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Per-step metadata: duration, cost, model used, etc.",
    )
