"""Platform Workflow & Resource Router — skeleton endpoints.

These endpoints expose the workflow run ledger and resource types for
read / query.  They are deliberately minimal — the goal is to provide
a stable API surface so that future expansion (agent-integrated workflow
dispatch, admin dashboards, capability-backed steps) can target real
routes without a routing rewrite.

All responses use the unified ApiResponse shape per project convention.
Future expansion: add POST/PUT endpoints for definition CRUD and
workflow dispatch as the orchestrator matures.
"""
import json
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.schemas.common import ApiResponse
from app.schemas.platform_resource import ResourceType
from app.models.platform_workflow import (
    WorkflowDefinition,
    WorkflowRunRecord,
    WorkflowStepRecord,
)

logger = logging.getLogger("v2.routers.workflow")
router = APIRouter(prefix="/api/workflow", tags=["platform-workflow"])


# ── Resource type listing (the "resource catalog") ────────────────


@router.get("/resource-types")
async def list_resource_types(_user=Depends(require_permission)):
    """Return the resource type catalog — all known resource categories
    in the platform resource graph.  This is the contract consumers
    should target when referencing resources."""
    return ApiResponse(data={
        "types": [t.value for t in ResourceType],
        "description": (
            "Every platform resource belongs to one of these categories. "
            "Use ResourceRef(id, resource_type) to reference any resource."
        ),
    })


# ── Workflow Definition ───────────────────────────────────────────


@router.get("/definitions")
async def list_definitions(
    status: str | None = Query(None),
    _user=Depends(require_permission),
    db: AsyncSession = Depends(get_db),
):
    """List workflow definitions, optionally filtered by status."""
    query = select(WorkflowDefinition)
    if status:
        query = query.where(WorkflowDefinition.status == status)
    query = query.order_by(WorkflowDefinition.updated_at.desc()).limit(100)
    result = await db.execute(query)
    definitions = result.scalars().all()
    return ApiResponse(data={
        "items": [_def_to_dict(d) for d in definitions],
        "total": len(definitions),
    })


@router.get("/definitions/{definition_id}")
async def get_definition(
    definition_id: int,
    _user=Depends(require_permission),
    db: AsyncSession = Depends(get_db),
):
    definition = await db.get(WorkflowDefinition, definition_id)
    if not definition:
        return ApiResponse(success=False, error="Workflow definition not found")
    return ApiResponse(data=_def_to_dict(definition))


# ── Workflow Run ──────────────────────────────────────────────────


@router.get("/runs")
async def list_runs(
    owner_id: int | None = Query(None),
    definition_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    _user=Depends(require_permission),
    db: AsyncSession = Depends(get_db),
):
    query = select(WorkflowRunRecord)
    if owner_id is not None:
        query = query.where(WorkflowRunRecord.owner_id == owner_id)
    if definition_id is not None:
        query = query.where(WorkflowRunRecord.definition_id == definition_id)
    if status is not None:
        query = query.where(WorkflowRunRecord.status == status)
    query = query.order_by(WorkflowRunRecord.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    runs = result.scalars().all()
    return ApiResponse(data={
        "items": [_run_to_dict(r) for r in runs],
        "total": len(runs),
    })


@router.get("/runs/{run_id}")
async def get_run(
    run_id: int,
    _user=Depends(require_permission),
    db: AsyncSession = Depends(get_db),
):
    run = await db.get(WorkflowRunRecord, run_id)
    if not run:
        return ApiResponse(success=False, error="Workflow run not found")
    return ApiResponse(data=_run_to_dict(run))


@router.get("/runs/{run_id}/steps")
async def get_run_steps(
    run_id: int,
    _user=Depends(require_permission),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(WorkflowStepRecord)
        .where(WorkflowStepRecord.run_id == run_id)
        .order_by(WorkflowStepRecord.created_at.asc())
    )
    result = await db.execute(query)
    steps = result.scalars().all()
    return ApiResponse(data={
        "items": [_step_to_dict(s) for s in steps],
        "total": len(steps),
    })


# ── Helpers ───────────────────────────────────────────────────────


def _def_to_dict(d: WorkflowDefinition) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "owner_id": d.owner_id,
        "status": d.status,
        "version": d.version,
        "node_count": len(d.nodes) if isinstance(d.nodes, list) else 0,
        "edge_count": len(d.edges) if isinstance(d.edges, list) else 0,
        "manifest": d.manifest,
        "created_at": str(d.created_at) if d.created_at else None,
        "updated_at": str(d.updated_at) if d.updated_at else None,
    }


def _run_to_dict(r: WorkflowRunRecord) -> dict:
    return {
        "id": r.id,
        "definition_id": r.definition_id,
        "owner_id": r.owner_id,
        "status": r.status,
        "trace": r.trace,
        "context": r.context,
        "error": r.error,
        "started_at": str(r.started_at) if r.started_at else None,
        "completed_at": str(r.completed_at) if r.completed_at else None,
        "created_at": str(r.created_at) if r.created_at else None,
        "updated_at": str(r.updated_at) if r.updated_at else None,
    }


def _step_to_dict(s: WorkflowStepRecord) -> dict:
    input_ref_raw = json.loads(s.input_ref) if s.input_ref else None
    output_ref_raw = json.loads(s.output_ref) if s.output_ref else None
    return {
        "id": s.id,
        "run_id": s.run_id,
        "node_id": s.node_id,
        "node_type": s.node_type,
        "status": s.status,
        "input_ref": input_ref_raw,
        "output_ref": output_ref_raw,
        "attempt": s.attempt,
        "error": s.error,
        "started_at": str(s.started_at) if s.started_at else None,
        "completed_at": str(s.completed_at) if s.completed_at else None,
        "created_at": str(s.created_at) if s.created_at else None,
        "updated_at": str(s.updated_at) if s.updated_at else None,
    }
