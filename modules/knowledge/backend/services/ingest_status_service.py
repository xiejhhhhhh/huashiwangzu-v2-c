"""Unified ingest status for knowledge documents."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.exceptions import NotFound
from app.models.system import SystemTaskQueue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    KbChunkEntity,
    KbDocument,
    KbDocumentProfile,
    KbFileRelation,
    KbGovernanceCandidate,
    KbGraphNode,
    KbPipelineRun,
    KbPipelineStageRun,
)
from .document_service import document_source_unavailable_reason

ACTIVE_TASK_STATUSES = {"pending", "running"}
FAILED_STAGE_STATUSES = {"failed", "error"}
DEGRADED_STAGE_STATUSES = {"degraded", "partial", "done_with_errors"}
RUNNING_STAGE_STATUSES = {"parsing", "indexing", "collecting", "running", "fusing"}
PARSER_NO_CONTENT_MARKER = "Parser returned no content blocks"


def _task_matches_document(task: SystemTaskQueue, document_id: int) -> bool:
    return task.document_id == int(document_id)


def _json_or_none(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    import json

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


async def find_latest_pipeline_task(
    db: AsyncSession,
    document_id: int,
) -> SystemTaskQueue | None:
    """Find the newest knowledge pipeline stage task for document_id."""
    document_id_value = int(document_id)
    result = await db.execute(
        select(SystemTaskQueue)
        .where(
            SystemTaskQueue.module == "knowledge",
            SystemTaskQueue.task_type == "kb_pipeline_stage",
            SystemTaskQueue.document_id == document_id_value,
        )
        .order_by(SystemTaskQueue.id.desc())
    )
    for task in result.scalars().all():
        if _task_matches_document(task, document_id):
            return task
    return None


def _stage(
    status: str | None,
    *,
    ready: bool | None = None,
    count: int | None = None,
    semantic: str | None = None,
    reason: str | None = None,
) -> dict:
    normalized = status or "pending"
    item = {
        "status": normalized,
        "ready": bool(ready) if ready is not None else normalized == "done",
    }
    if count is not None:
        item["count"] = count
    if semantic:
        item["semantic"] = semantic
    if reason:
        item["reason"] = reason
    return item


def _stage_run_lookup(rows: list[KbPipelineStageRun]) -> dict[str, KbPipelineStageRun]:
    lookup: dict[str, KbPipelineStageRun] = {}
    for row in rows:
        lookup[row.stage] = row
    return lookup


def _stage_semantic(stage_run: KbPipelineStageRun | None, ready: bool, count: int = 0) -> tuple[str | None, str | None]:
    if stage_run is None:
        return None, None
    if stage_run.status == "skipped":
        return "skipped", stage_run.reason
    if stage_run.status == "paused":
        return "paused", stage_run.reason
    if stage_run.status == "done" and count == 0:
        return "done_empty", stage_run.reason
    if ready or stage_run.status == "done":
        return "done_with_results", stage_run.reason
    return None, stage_run.reason


def _run_payload(run: KbPipelineRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "run_id": run.id,
        "status": run.status,
        "reason": run.reason,
        "diagnostics": run.diagnostics_json,
        "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at),
    }


def _task_payload(task: SystemTaskQueue | None) -> dict | None:
    if task is None:
        return None
    return {
        "task_id": task.id,
        "task_type": task.task_type,
        "stage": getattr(task, "stage_key", None),
        "lane": getattr(task, "lane_key", None),
        "ready_status": getattr(task, "ready_status", None),
        "dependency_key": getattr(task, "dependency_key", None),
        "status": task.status,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "error_message": task.error_message,
        "result": _json_or_none(task.result),
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
        "started_at": _iso(task.started_at),
        "completed_at": _iso(task.completed_at),
    }


def build_ingest_status_payload(
    doc: KbDocument,
    task: SystemTaskQueue | None,
    *,
    profile_count: int = 0,
    graph_entity_count: int = 0,
    graph_node_count: int = 0,
    chunk_entity_count: int = 0,
    relation_count: int = 0,
    source_available: bool = True,
    source_state: str = "available",
    latest_run: KbPipelineRun | None = None,
    stage_runs: list[KbPipelineStageRun] | None = None,
) -> dict:
    """Build the stable ingest status contract from document + queue state."""
    parse_status = doc.parse_status or "pending"
    vector_status = doc.vector_status or "pending"
    raw_status = getattr(doc, "raw_status", "pending") or "pending"
    fusion_status = getattr(doc, "fusion_status", "pending") or "pending"
    profile_status = getattr(doc, "profile_status", "pending") or "pending"
    graph_status = getattr(doc, "graph_status", "pending") or "pending"
    relation_status = getattr(doc, "relation_status", "pending") or "pending"
    task_status = task.status if task is not None else None
    task_result = _json_or_none(task.result if task is not None else None) or {}
    active_task_stage = str(getattr(task, "stage_key", "") if task is not None else "")
    latest_run_status = latest_run.status if latest_run is not None else ""
    latest_run_reason = latest_run.reason if latest_run is not None else ""
    stored_source_reason = document_source_unavailable_reason(doc)
    if stored_source_reason:
        source_available = False
        source_state = stored_source_reason
    elif not source_available and not source_state:
        source_state = "source_unavailable"
    elif source_available:
        source_state = "available"

    parse_ready = source_available and (
        parse_status == "done" or (
            parse_status == "degraded"
            and PARSER_NO_CONTENT_MARKER.lower() in (doc.parse_error or "").lower()
        )
    )

    search_ready = (
        source_available
        and parse_ready
        and vector_status == "done"
        and (doc.total_chunks or 0) > 0
    )
    paused = source_available and latest_run_status == "paused"
    effective_profile_status = "done" if profile_status == "pending" and profile_count > 0 else profile_status
    effective_graph_status = "done" if graph_status == "pending" and graph_entity_count > 0 else graph_status
    effective_relation_status = "done" if relation_status == "pending" and relation_count > 0 else relation_status
    deep_ready = (
        source_available
        and raw_status == "done"
        and fusion_status == "done"
        and effective_profile_status == "done"
        and effective_graph_status == "done"
        and effective_relation_status == "done"
        and not paused
    )
    profile_ready = source_available and effective_profile_status == "done"
    graph_ready = source_available and effective_graph_status == "done"
    relation_ready = source_available and effective_relation_status == "done"
    stage_lookup = _stage_run_lookup(stage_runs or [])
    raw_semantic, raw_reason = _stage_semantic(stage_lookup.get("raw"), raw_status == "done", 1 if raw_status == "done" else 0)
    fusion_semantic, fusion_reason = _stage_semantic(stage_lookup.get("fusion"), fusion_status == "done", 1 if fusion_status == "done" else 0)
    profile_semantic, profile_reason = _stage_semantic(stage_lookup.get("profile"), profile_ready, profile_count)
    graph_semantic, graph_reason = _stage_semantic(stage_lookup.get("graph"), graph_ready, graph_entity_count)
    relation_semantic, relation_reason = _stage_semantic(stage_lookup.get("relations"), relation_ready, relation_count)
    pause_semantic, pause_reason = _stage_semantic(stage_lookup.get("pause"), False, 0)
    stage_summary = {
        "parse": _stage(parse_status, ready=parse_ready),
        "vector": _stage(vector_status, ready=search_ready, count=doc.total_chunks or 0),
        "raw": _stage(raw_status, ready=source_available and raw_status == "done", semantic=raw_semantic, reason=raw_reason),
        "fusion": _stage(fusion_status, ready=source_available and fusion_status == "done", semantic=fusion_semantic, reason=fusion_reason),
        "profile": _stage(effective_profile_status, ready=profile_ready, count=profile_count, semantic=profile_semantic, reason=profile_reason),
        "graph": _stage(effective_graph_status, ready=graph_ready, count=graph_entity_count, semantic=graph_semantic, reason=graph_reason),
        "relation": _stage(effective_relation_status, ready=relation_ready, count=relation_count, semantic=relation_semantic, reason=relation_reason),
    }
    if pause_semantic:
        stage_summary["pause"] = _stage("paused", ready=False, semantic=pause_semantic, reason=pause_reason)
    stage_summary["graph"]["node_count"] = graph_node_count
    stage_summary["graph"]["chunk_entity_count"] = chunk_entity_count

    stage_order = ("parse", "vector", "raw", "fusion", "profile", "graph", "relation")
    current_stage = "source" if not source_available else next(
        (key for key in stage_order if not stage_summary[key]["ready"]),
        "complete",
    )
    if task_status in ACTIVE_TASK_STATUSES and active_task_stage:
        current_stage = active_task_stage
    if paused:
        current_stage = "paused"
    if not source_available:
        last_error = source_state
    else:
        last_error = latest_run_reason or (
            task.error_message if task is not None and task.error_message else None
        ) or doc.parse_error or task_result.get("error")

    all_stage_statuses = (
        parse_status,
        vector_status,
        raw_status,
        fusion_status,
        effective_profile_status,
        effective_graph_status,
        effective_relation_status,
    )

    if not source_available:
        pipeline_status = "source_unavailable"
    elif paused:
        pipeline_status = "paused"
    elif any(s in FAILED_STAGE_STATUSES for s in all_stage_statuses):
        pipeline_status = "failed"
    elif task_status == "failed":
        pipeline_status = "failed"
    elif any(s in DEGRADED_STAGE_STATUSES for s in all_stage_statuses):
        pipeline_status = "degraded"
    elif task_result.get("status") in DEGRADED_STAGE_STATUSES:
        pipeline_status = "degraded"
    elif task_status == "running" or any(
        s in RUNNING_STAGE_STATUSES for s in all_stage_statuses
    ):
        pipeline_status = "running"
    elif task_status == "pending":
        pipeline_status = "queued"
    elif search_ready and deep_ready:
        pipeline_status = "deep_ready"
    elif search_ready:
        pipeline_status = "search_ready"
    else:
        pipeline_status = "pending"

    if pipeline_status == "source_unavailable":
        next_action = "restore_source_or_archive_document"
    elif pipeline_status == "paused":
        next_action = "review_model_degradation_before_resume"
    elif pipeline_status == "failed":
        next_action = "inspect_error_or_retry_pipeline"
    elif pipeline_status == "degraded":
        next_action = "inspect_degraded_or_retry_pipeline"
    elif not search_ready and task_status in ACTIVE_TASK_STATUSES:
        next_action = "wait_for_search_index"
    elif not search_ready:
        next_action = "enqueue_or_parse_document"
    elif not deep_ready and task_status in ACTIVE_TASK_STATUSES:
        next_action = "wait_for_deep_analysis"
    elif not deep_ready:
        next_action = "enqueue_full_pipeline"
    else:
        next_action = "ready"

    return {
        "document_id": doc.id,
        "file_id": doc.file_id,
        "filename": doc.filename,
        "source_available": source_available,
        "source_state": source_state,
        "task_id": task.id if task is not None else None,
        "enqueued": task_status == "pending" if task_status else False,
        "stage": current_stage,
        "status": pipeline_status,
        "pipeline_status": pipeline_status,
        "task_status": task_status,
        "task": _task_payload(task),
        "latest_run": _run_payload(latest_run),
        "parse_status": parse_status,
        "vector_status": vector_status,
        "raw_status": raw_status,
        "fusion_status": fusion_status,
        "stage_summary": stage_summary,
        "search_ready": search_ready,
        "deep_ready": deep_ready,
        "last_error": last_error,
        "next_action": next_action,
    }


async def get_ingest_status(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
) -> dict:
    """Return a caller-scoped ingest status for one knowledge document."""
    from .source_file_state import get_source_file_availability

    result = await db.execute(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted.is_(False),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFound("Document not found")

    source = await get_source_file_availability(db, int(doc.file_id or 0))

    profile_count = await db.scalar(
        select(func.count(KbDocumentProfile.id)).where(
            KbDocumentProfile.document_id == document_id,
            KbDocumentProfile.owner_id == owner_id,
        )
    ) or 0
    candidate_count = await db.scalar(
        select(func.count(KbGovernanceCandidate.id)).where(
            KbGovernanceCandidate.document_id == document_id,
            KbGovernanceCandidate.owner_id == owner_id,
        )
    ) or 0
    chunk_entity_count = await db.scalar(
        select(func.count(KbChunkEntity.id)).where(
            KbChunkEntity.document_id == document_id,
            KbChunkEntity.owner_id == owner_id,
        )
    ) or 0
    graph_node_count = await db.scalar(
        select(func.count(KbGraphNode.id)).where(KbGraphNode.owner_id == owner_id)
    ) or 0
    graph_entity_count = max(candidate_count, chunk_entity_count)
    relation_count = await db.scalar(
        select(func.count(KbFileRelation.id)).where(
            KbFileRelation.owner_id == owner_id,
            (KbFileRelation.source_document_id == document_id)
            | (KbFileRelation.target_document_id == document_id),
        )
    ) or 0
    task = await find_latest_pipeline_task(db, document_id)
    latest_run = await db.scalar(
        select(KbPipelineRun)
        .where(
            KbPipelineRun.document_id == document_id,
            KbPipelineRun.owner_id == owner_id,
        )
        .order_by(KbPipelineRun.id.desc())
        .limit(1)
    )
    stage_runs = []
    if latest_run is not None:
        stage_run_result = await db.execute(
            select(KbPipelineStageRun)
            .where(KbPipelineStageRun.run_id == latest_run.id)
            .order_by(KbPipelineStageRun.id)
        )
        stage_runs = list(stage_run_result.scalars().all())
    return build_ingest_status_payload(
        doc,
        task,
        profile_count=profile_count,
        graph_entity_count=graph_entity_count,
        graph_node_count=graph_node_count,
        chunk_entity_count=chunk_entity_count,
        relation_count=relation_count,
        source_available=source.available,
        source_state=source.reason or "available",
        latest_run=latest_run,
        stage_runs=stage_runs,
    )
