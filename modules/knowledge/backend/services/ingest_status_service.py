"""Unified ingest status for knowledge documents.

The queue table is framework-owned, but knowledge owns the business meaning of
its kb_pipeline tasks. This service reads queue rows by parsing task parameters
for document_id so callers can distinguish "queued" from "searchable" and
"deep analysis complete".
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.core.exceptions import NotFound
from app.models.system import SystemTaskQueue
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    KbChunkEntity,
    KbDocument,
    KbDocumentProfile,
    KbFileRelation,
    KbGovernanceCandidate,
    KbGraphNode,
)
from .document_service import document_source_unavailable_reason

ACTIVE_TASK_STATUSES = {"pending", "running"}
FAILED_STAGE_STATUSES = {"failed", "error"}
DEGRADED_STAGE_STATUSES = {"degraded", "partial", "done_with_errors"}
RUNNING_STAGE_STATUSES = {"parsing", "indexing", "collecting", "running", "fusing"}
PARSER_NO_CONTENT_MARKER = "Parser returned no content blocks"


def _load_task_parameters(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _task_matches_document(task: SystemTaskQueue, document_id: int) -> bool:
    params = _load_task_parameters(task.parameters)
    try:
        return int(params.get("document_id", 0) or 0) == int(document_id)
    except (TypeError, ValueError):
        return False


def _json_or_none(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
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
    """Find the newest kb_pipeline task whose parameters name document_id."""
    document_id_value = int(document_id)
    # Narrow in SQL first. Historical queue rows store parameters as text JSON, so
    # keep the final Python parser as the contract check while avoiding a full
    # table scan on every status poll.
    needle_with_space = f'"document_id": {document_id_value}'
    needle_without_space = f'"document_id":{document_id_value}'
    result = await db.execute(
        select(SystemTaskQueue)
        .where(
            SystemTaskQueue.module == "knowledge",
            SystemTaskQueue.task_type == "kb_pipeline",
            or_(
                SystemTaskQueue.parameters.contains(needle_with_space),
                SystemTaskQueue.parameters.contains(needle_without_space),
            ),
        )
        .order_by(SystemTaskQueue.id.desc())
    )
    for task in result.scalars().all():
        if _task_matches_document(task, document_id):
            return task
    return None


def _stage(status: str | None, *, ready: bool | None = None, count: int | None = None) -> dict:
    normalized = status or "pending"
    item = {
        "status": normalized,
        "ready": bool(ready) if ready is not None else normalized == "done",
    }
    if count is not None:
        item["count"] = count
    return item


def _task_payload(task: SystemTaskQueue | None) -> dict | None:
    if task is None:
        return None
    return {
        "task_id": task.id,
        "task_type": task.task_type,
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
) -> dict:
    """Build the stable ingest status contract from document + queue state."""
    parse_status = doc.parse_status or "pending"
    vector_status = doc.vector_status or "pending"
    raw_status = getattr(doc, "raw_status", "pending") or "pending"
    fusion_status = getattr(doc, "fusion_status", "pending") or "pending"
    task_status = task.status if task is not None else None
    task_result = _json_or_none(task.result if task is not None else None) or {}
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
    deep_ready = source_available and raw_status == "done" and fusion_status == "done"
    profile_ready = source_available and profile_count > 0
    graph_ready = source_available and graph_entity_count > 0
    relation_ready = source_available and relation_count > 0
    stage_summary = {
        "parse": _stage(parse_status, ready=parse_ready),
        "vector": _stage(vector_status, ready=search_ready, count=doc.total_chunks or 0),
        "raw": _stage(raw_status, ready=source_available and raw_status == "done"),
        "fusion": _stage(fusion_status, ready=source_available and fusion_status == "done"),
        "profile": _stage("done" if profile_count > 0 else "pending", ready=profile_ready, count=profile_count),
        "graph": _stage("done" if graph_entity_count > 0 else "pending", ready=graph_ready, count=graph_entity_count),
        "relation": _stage("done" if relation_count > 0 else "pending", ready=relation_ready, count=relation_count),
    }
    stage_summary["graph"]["node_count"] = graph_node_count
    stage_summary["graph"]["chunk_entity_count"] = chunk_entity_count

    stage_order = ("parse", "vector", "raw", "fusion", "profile", "graph", "relation")
    current_stage = "source" if not source_available else next(
        (key for key in stage_order if not stage_summary[key]["ready"]),
        "complete",
    )
    if not source_available:
        last_error = source_state
    else:
        last_error = (
            task.error_message if task is not None and task.error_message else None
        ) or doc.parse_error or task_result.get("error")

    if not source_available:
        pipeline_status = "source_unavailable"
    elif any(s in FAILED_STAGE_STATUSES for s in (parse_status, vector_status, raw_status, fusion_status)):
        pipeline_status = "failed"
    elif task_status == "failed":
        pipeline_status = "failed"
    elif any(s in DEGRADED_STAGE_STATUSES for s in (parse_status, vector_status, raw_status, fusion_status)):
        pipeline_status = "degraded"
    elif task_result.get("status") in DEGRADED_STAGE_STATUSES:
        pipeline_status = "degraded"
    elif task_status == "running" or any(
        s in RUNNING_STAGE_STATUSES for s in (parse_status, vector_status, raw_status, fusion_status)
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
    )
