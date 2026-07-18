"""Knowledge dashboard stats service.

Pure service layer: accepts db + user_id, returns dict.
Router layer is responsible for ApiResponse wrapping and auth.
"""
import json
import logging
import os
from pathlib import Path

from app.config import get_settings
from app.models.file import File
from app.models.system import SystemTaskQueue
from sqlalchemy import and_, case, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..models import (
    KbDocument,
    KbEntityDictionary,
    KbFileRelation,
    KbGraphEdge,
)

logger = logging.getLogger("v2.knowledge").getChild("dashboard_service")

DEEP_STAGE_ATTRS = (
    "raw_status",
    "fusion_status",
    "profile_status",
    "graph_status",
    "relation_status",
)
DEEP_STAGE_FIELDS = tuple(getattr(KbDocument, attr) for attr in DEEP_STAGE_ATTRS)
FAILED_STAGE_STATUSES = {"failed", "error"}
RUNNING_STAGE_STATUSES = {"running", "collecting", "parsing", "fusing", "indexing"}
DEGRADED_STAGE_STATUSES = {"degraded", "partial", "done_with_errors"}
PAUSED_STAGE_STATUSES = {"paused"}
PENDING_STAGE_STATUSES = {"pending", ""}
TASK_STAGE_TO_DOC_ATTR = {
    "parse_index": "raw_status",
    "raw_text": "raw_status",
    "raw_ocr": "raw_status",
    "raw_vision": "raw_status",
    "fusion": "fusion_status",
    "profile": "profile_status",
    "graph": "graph_status",
    "relations": "relation_status",
}
SOURCE_UNAVAILABLE_REASONS = {
    "source_file_deleted",
    "source_file_missing",
    "source_storage_path_missing",
    "source_path_unsafe",
    "source_file_physical_missing",
}
NON_CONTENT_FILE_REASONS = {
    "non_content_appledouble_sidecar",
    "non_content_office_lock_file",
    "non_content_windows_recycle_metadata_file",
}
PIPELINE_TASK_TYPE = "kb_pipeline_stage"


def _source_state(file: File | None) -> tuple[bool, str]:
    if file is None:
        return False, "source_file_missing"
    storage_path = str(file.storage_path or "").strip()
    if file.deleted:
        return False, "source_file_deleted"
    if not storage_path:
        return False, "source_storage_path_missing"
    upload_root = Path(get_settings().UPLOAD_DIR).resolve()
    try:
        full_path = (upload_root / storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
            return False, "source_path_unsafe"
        if not full_path.is_file():
            return False, "source_file_physical_missing"
    except (OSError, ValueError):
        return False, "source_path_unsafe"
    return True, "available"


def _load_paused_worker_config() -> tuple[set[str], set[str]]:
    path = Path(__file__).resolve().parents[4] / "backend" / "data" / "config" / "task_worker.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), set()
    paused_stages = raw.get("paused_stages") or {}
    paused_lanes = raw.get("paused_lanes") or {}
    return (
        {str(item) for item in (paused_stages.get(PIPELINE_TASK_TYPE) or [])},
        {str(item) for item in (paused_lanes.get(PIPELINE_TASK_TYPE) or [])},
    )


def _task_is_paused(task: SystemTaskQueue | None, paused_stages: set[str], paused_lanes: set[str]) -> bool:
    if task is None:
        return False
    stage = str(task.stage_key or "")
    lane = str(task.lane_key or "")
    return stage in paused_stages or lane in paused_lanes


def _latest_task_by_document(tasks: list[SystemTaskQueue]) -> dict[int, SystemTaskQueue]:
    latest: dict[int, SystemTaskQueue] = {}
    for task in tasks:
        if task.document_id is None:
            continue
        doc_id = int(task.document_id)
        current = latest.get(doc_id)
        if current is None or int(task.id) > int(current.id):
            latest[doc_id] = task
    return latest


def _task_display_status(task: SystemTaskQueue | None, paused_stages: set[str], paused_lanes: set[str]) -> str | None:
    if task is None:
        return None
    if task.status == "running":
        return "running"
    if task.status == "pending":
        if _task_is_paused(task, paused_stages, paused_lanes):
            return "paused"
        if getattr(task, "ready_status", None) not in (None, "", "ready"):
            return "waiting"
        return "queued"
    if task.status == "failed":
        return "failed"
    return None


def _stage_statuses(doc: KbDocument, task: SystemTaskQueue | None, task_status: str | None) -> dict[str, str]:
    statuses = {attr: str(getattr(doc, attr, "pending") or "pending") for attr in DEEP_STAGE_ATTRS}
    if task is None or task_status is None:
        return statuses
    doc_attr = TASK_STAGE_TO_DOC_ATTR.get(str(task.stage_key or ""))
    if doc_attr and statuses.get(doc_attr, "pending") in PENDING_STAGE_STATUSES | RUNNING_STAGE_STATUSES:
        statuses[doc_attr] = task_status
    return statuses


def _document_bucket(
    statuses: dict[str, str],
    task: SystemTaskQueue | None,
    task_status: str | None,
    *,
    source_available: bool,
) -> str:
    values = set(statuses.values())
    if not source_available:
        return "source_unavailable"
    if any(status in FAILED_STAGE_STATUSES for status in values) or task_status == "failed":
        return "failed"
    if all(status == "done" for status in values):
        return "completed"
    if task_status == "running" or any(status in RUNNING_STAGE_STATUSES for status in values):
        return "running"
    if task_status == "paused" or any(status in PAUSED_STAGE_STATUSES for status in values):
        return "paused"
    if task_status == "queued":
        return "queued"
    if task_status == "waiting":
        return "waiting"
    if any(status in DEGRADED_STAGE_STATUSES for status in values):
        return "partial"
    if any(status in PENDING_STAGE_STATUSES for status in values):
        return "waiting"
    return "partial"


def _dashboard_source_state(file: File | None, parse_error: str) -> tuple[bool, str]:
    if file is None:
        return False, "source_file_missing"
    if file.deleted:
        return False, "source_file_deleted"
    if not str(file.storage_path or "").strip():
        return False, "source_storage_path_missing"
    if parse_error in NON_CONTENT_FILE_REASONS:
        return True, parse_error
    return True, "available"


def _dashboard_bucket_expression(
    latest_task: type[SystemTaskQueue],
    paused_stages: set[str],
    paused_lanes: set[str],
):
    stage_values = [func.coalesce(field, "pending") for field in DEEP_STAGE_FIELDS]
    paused_terms = []
    if paused_stages:
        paused_terms.append(latest_task.stage_key.in_(tuple(paused_stages)))
    if paused_lanes:
        paused_terms.append(latest_task.lane_key.in_(tuple(paused_lanes)))
    worker_paused = or_(*paused_terms) if paused_terms else false()
    task_ready = or_(latest_task.ready_status.is_(None), latest_task.ready_status.in_(("", "ready")))
    source_unavailable = or_(
        File.id.is_(None),
        File.deleted.is_(True),
        func.coalesce(File.storage_path, "") == "",
    )
    failed = or_(
        latest_task.status == "failed",
        *(value.in_(tuple(FAILED_STAGE_STATUSES)) for value in stage_values),
    )
    completed = and_(*(value == "done" for value in stage_values))
    running = or_(
        latest_task.status == "running",
        *(value.in_(tuple(RUNNING_STAGE_STATUSES)) for value in stage_values),
    )
    paused = or_(
        and_(latest_task.status == "pending", worker_paused),
        *(value.in_(tuple(PAUSED_STAGE_STATUSES)) for value in stage_values),
    )
    queued = and_(latest_task.status == "pending", ~worker_paused, task_ready)
    task_waiting = and_(latest_task.status == "pending", ~task_ready)
    degraded = or_(*(value.in_(tuple(DEGRADED_STAGE_STATUSES)) for value in stage_values))
    pending = or_(*(value.in_(tuple(PENDING_STAGE_STATUSES)) for value in stage_values))
    return case(
        (source_unavailable, "source_unavailable"),
        (failed, "failed"),
        (completed, "completed"),
        (running, "running"),
        (paused, "paused"),
        (queued, "queued"),
        (task_waiting, "waiting"),
        (degraded, "partial"),
        (pending, "waiting"),
        else_="partial",
    )


def _dashboard_entry(
    doc: KbDocument,
    file: File | None,
    task: SystemTaskQueue | None,
    paused_stages: set[str],
    paused_lanes: set[str],
) -> dict:
    parse_error = str(doc.parse_error or "")
    source_available, source_state = _dashboard_source_state(file, parse_error)
    task_status = _task_display_status(task, paused_stages, paused_lanes)
    statuses = _stage_statuses(doc, task, task_status)
    bucket = _document_bucket(statuses, task, task_status, source_available=source_available)
    return {
        "id": doc.id, "filename": doc.filename, "total_pages": doc.total_pages,
        "raw_status": statuses["raw_status"], "fusion_status": statuses["fusion_status"],
        "profile_status": statuses["profile_status"], "graph_status": statuses["graph_status"],
        "relation_status": statuses["relation_status"],
        "parse_status": doc.parse_status, "created_at": str(doc.created_at or ""),
        "source_available": bool(source_available), "source_state": source_state,
        "pipeline_status": bucket,
        "task_status": task.status if task is not None else None,
        "task_stage": task.stage_key if task is not None else None,
    }


async def get_dashboard_stats(
    db: AsyncSession,
    user_id: int,
    *,
    page: int = 1,
    page_size: int = 50,
    include_analytics: bool = False,
) -> dict:
    live_source_clause = exists(
        select(File.id).where(
            File.id == KbDocument.file_id,
            File.deleted.is_(False),
        )
    )
    paused_stages, paused_lanes = _load_paused_worker_config()
    latest_task_ids = (
        select(
            SystemTaskQueue.document_id.label("document_id"),
            func.max(SystemTaskQueue.id).label("id"),
        )
        .where(
            SystemTaskQueue.module == "knowledge",
            SystemTaskQueue.task_type == PIPELINE_TASK_TYPE,
            SystemTaskQueue.document_id.is_not(None),
            SystemTaskQueue.document_id.in_(
                select(KbDocument.id).where(
                    KbDocument.deleted.is_(False),
                    KbDocument.owner_id == user_id,
                )
            ),
        )
        .group_by(SystemTaskQueue.document_id)
        .subquery()
    )
    latest_task = aliased(SystemTaskQueue)
    bucket_expr = _dashboard_bucket_expression(latest_task, paused_stages, paused_lanes)
    base_filters = (KbDocument.deleted.is_(False), KbDocument.owner_id == user_id)
    counter_rows = (await db.execute(
        select(bucket_expr.label("bucket"), func.count(KbDocument.id))
        .select_from(KbDocument)
        .outerjoin(File, File.id == KbDocument.file_id)
        .outerjoin(latest_task_ids, latest_task_ids.c.document_id == KbDocument.id)
        .outerjoin(latest_task, latest_task.id == latest_task_ids.c.id)
        .where(*base_filters)
        .group_by(bucket_expr)
    )).all()
    counters = {
        "completed": 0,
        "failed": 0,
        "partial": 0,
        "running": 0,
        "queued": 0,
        "paused": 0,
        "waiting": 0,
        "source_unavailable": 0,
    }
    for bucket, count in counter_rows:
        counters[str(bucket)] = int(count or 0)
    page_rows = (await db.execute(
        select(KbDocument, File, latest_task)
        .select_from(KbDocument)
        .outerjoin(File, File.id == KbDocument.file_id)
        .outerjoin(latest_task_ids, latest_task_ids.c.document_id == KbDocument.id)
        .outerjoin(latest_task, latest_task.id == latest_task_ids.c.id)
        .where(*base_filters)
        .order_by(KbDocument.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).all()
    doc_progresses = [
        _dashboard_entry(doc, file, task, paused_stages, paused_lanes)
        for doc, file, task in page_rows
    ]
    stuck_rows = []
    if counters["failed"] or counters["source_unavailable"]:
        stuck_rows = (await db.execute(
            select(KbDocument, File, latest_task)
            .select_from(KbDocument)
            .outerjoin(File, File.id == KbDocument.file_id)
            .outerjoin(latest_task_ids, latest_task_ids.c.document_id == KbDocument.id)
            .outerjoin(latest_task, latest_task.id == latest_task_ids.c.id)
            .where(*base_filters, bucket_expr.in_(("failed", "source_unavailable")))
            .order_by(KbDocument.id.desc())
            .limit(20)
        )).all()
    stuck_docs = [
        _dashboard_entry(doc, file, task, paused_stages, paused_lanes)
        for doc, file, task in stuck_rows
    ]

    total = sum(counters.values())
    completed = counters["completed"]
    failed = counters["failed"]
    partial = counters["partial"]
    running = counters["running"]
    queued = counters["queued"]
    paused = counters["paused"]
    waiting = counters["waiting"]
    source_unavailable = counters["source_unavailable"]

    entity_count = 0
    relation_count = 0
    file_relation_count = 0
    duplicate_entities = 0
    dup_groups = []
    entity_category_distribution = {}
    if include_analytics:
        entity_count = (await db.execute(
            select(func.count(KbEntityDictionary.id)).where(KbEntityDictionary.owner_id == user_id)
        )).scalar() or 0
        relation_count = (await db.execute(
            select(func.count(KbGraphEdge.id)).where(KbGraphEdge.owner_id == user_id)
        )).scalar() or 0
        file_relation_count = (await db.execute(
            select(func.count(KbFileRelation.id)).where(KbFileRelation.owner_id == user_id)
        )).scalar() or 0
        dup_rows = await db.execute(
            select(KbEntityDictionary.name, func.count(KbEntityDictionary.id))
            .where(KbEntityDictionary.owner_id == user_id, KbEntityDictionary.status != "merged")
            .group_by(KbEntityDictionary.name)
            .having(func.count(KbEntityDictionary.id) > 1)
        )
        dup_groups = dup_rows.all()
        duplicate_entities = sum(cnt for _, cnt in dup_groups)
        cat_rows = await db.execute(
            select(KbEntityDictionary.category, func.count(KbEntityDictionary.id))
            .where(KbEntityDictionary.owner_id == user_id)
            .group_by(KbEntityDictionary.category)
            .order_by(func.count(KbEntityDictionary.id).desc())
        )
        entity_category_distribution = {cat: cnt for cat, cnt in cat_rows.all()}

    recent = (await db.execute(
        select(KbDocument).where(
            KbDocument.deleted.is_(False), KbDocument.owner_id == user_id,
            live_source_clause,
            KbDocument.raw_status == "done",
            KbDocument.fusion_status == "done",
            KbDocument.profile_status == "done",
            KbDocument.graph_status == "done",
            KbDocument.relation_status == "done",
        )
        .order_by(KbDocument.updated_at.desc().nullslast())
        .limit(10)
    )).scalars().all()
    recent_completions = [
        {"id": d.id, "filename": d.filename, "completed_at": str(d.updated_at or "")}
        for d in recent
    ]

    return {
        "total_documents": total,
        "completed_documents": completed,
        "partial_documents": partial,
        "running_documents": running,
        "queued_documents": queued,
        "paused_documents": paused,
        "waiting_documents": waiting,
        "failed_documents": failed,
        "source_unavailable_documents": source_unavailable,
        "total_entities": entity_count,
        "total_graph_relations": relation_count,
        "total_file_relations": file_relation_count,
        "duplicate_entity_count": duplicate_entities,
        "duplicate_entity_groups": [{"name": name, "count": cnt} for name, cnt in dup_groups[:20]],
        "entity_category_distribution": entity_category_distribution,
        "document_progresses": doc_progresses,
        "document_progress_total": total,
        "document_progress_page": page,
        "document_progress_page_size": page_size,
        "stuck_documents": stuck_docs,
        "recent_completions": recent_completions,
        "analytics_loaded": include_analytics,
    }
