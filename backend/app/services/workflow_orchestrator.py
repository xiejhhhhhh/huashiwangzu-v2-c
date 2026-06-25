"""Platform Workflow Orchestrator — minimal skeleton.

This service is the entry point for creating and tracking workflow runs.
It does NOT implement a full Dify/Coze-style orchestrator; it provides
the minimum surface needed to:
1. Create a workflow run from a definition
2. Record step progress (start / complete / fail)
3. Query run and step status
4. Reference resources via ResourceRef

Future expansion points (marked with ``# FUTURE:``) show where
state-machine logic, conditional routing, sub-workflow dispatch,
and compensation handlers would attach.
"""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_workflow import (
    WorkflowDefinition,
    WorkflowRunRecord,
    WorkflowStepRecord,
)
from app.schemas.platform_resource import ResourceRef

logger = logging.getLogger("v2.workflow_orchestrator")


# ── Workflow Run Lifecycle ──────────────────────────────────────────


async def create_run(
    db: AsyncSession,
    definition_id: int,
    owner_id: int,
    context: dict | None = None,
    trace: str | None = None,
) -> WorkflowRunRecord:
    """Create a new workflow run in ``pending`` status.

    Does NOT start execution — call ``start_run()`` when the
    orchestrator is ready to dispatch.
    """
    definition = await db.get(WorkflowDefinition, definition_id)
    if not definition:
        raise ValueError(f"WorkflowDefinition {definition_id} not found")

    run = WorkflowRunRecord(
        definition_id=definition_id,
        owner_id=owner_id,
        status="pending",
        context=context or {},
        trace=trace,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    logger.info("Workflow run %s created (definition=%s, owner=%s)", run.id, definition_id, owner_id)
    return run


async def start_run(db: AsyncSession, run_id: int) -> WorkflowRunRecord | None:
    """Transition a run from ``pending`` to ``running``."""
    run = await db.get(WorkflowRunRecord, run_id)
    if not run:
        return None
    if run.status != "pending":
        logger.warning("Cannot start run %s: current status=%s", run_id, run.status)
        return run
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


async def complete_run(
    db: AsyncSession,
    run_id: int,
    error: str | None = None,
) -> WorkflowRunRecord | None:
    """Mark a run as ``completed`` or ``failed``."""
    run = await db.get(WorkflowRunRecord, run_id)
    if not run:
        return None
    run.status = "failed" if error else "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.error = error
    await db.commit()
    await db.refresh(run)
    return run


async def cancel_run(db: AsyncSession, run_id: int) -> WorkflowRunRecord | None:
    """Cancel a run regardless of current status."""
    run = await db.get(WorkflowRunRecord, run_id)
    if not run:
        return None
    run.status = "cancelled"
    run.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


# ── Step Lifecycle ──────────────────────────────────────────────────


async def create_step(
    db: AsyncSession,
    run_id: int,
    node_id: str,
    node_type: str = "task",
    input_ref: list[ResourceRef] | None = None,
) -> WorkflowStepRecord:
    """Create a step record for a workflow run node."""
    step = WorkflowStepRecord(
        run_id=run_id,
        node_id=node_id,
        node_type=node_type,
        status="pending",
        input_ref=json.dumps([r.model_dump() for r in input_ref]) if input_ref else None,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def start_step(db: AsyncSession, step_id: int) -> WorkflowStepRecord | None:
    """Mark a step as ``running``."""
    step = await db.get(WorkflowStepRecord, step_id)
    if not step:
        return None
    step.status = "running"
    step.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(step)
    return step


async def complete_step(
    db: AsyncSession,
    step_id: int,
    output_ref: list[ResourceRef] | None = None,
    error: str | None = None,
) -> WorkflowStepRecord | None:
    """Mark a step as ``completed`` or ``failed``."""
    step = await db.get(WorkflowStepRecord, step_id)
    if not step:
        return None
    step.status = "failed" if error else "completed"
    step.completed_at = datetime.now(timezone.utc)
    step.error = error
    if output_ref:
        step.output_ref = json.dumps([r.model_dump() for r in output_ref])
    await db.commit()
    await db.refresh(step)
    return step


# ── Queries ─────────────────────────────────────────────────────────


async def get_run(db: AsyncSession, run_id: int) -> WorkflowRunRecord | None:
    return await db.get(WorkflowRunRecord, run_id)


async def list_runs(
    db: AsyncSession,
    owner_id: int | None = None,
    definition_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[WorkflowRunRecord]:
    query = select(WorkflowRunRecord)
    if owner_id is not None:
        query = query.where(WorkflowRunRecord.owner_id == owner_id)
    if definition_id is not None:
        query = query.where(WorkflowRunRecord.definition_id == definition_id)
    if status is not None:
        query = query.where(WorkflowRunRecord.status == status)
    query = query.order_by(WorkflowRunRecord.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_steps(db: AsyncSession, run_id: int) -> list[WorkflowStepRecord]:
    query = (
        select(WorkflowStepRecord)
        .where(WorkflowStepRecord.run_id == run_id)
        .order_by(WorkflowStepRecord.created_at.asc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())
