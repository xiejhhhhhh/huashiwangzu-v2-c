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
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def get_dashboard_stats(db: AsyncSession, user_id: int) -> dict:
    live_source_clause = exists(
        select(File.id).where(
            File.id == KbDocument.file_id,
            File.deleted.is_(False),
        )
    )
    all_docs_result = await db.execute(
        select(KbDocument, File)
        .join(File, File.id == KbDocument.file_id, isouter=True)
        .where(KbDocument.deleted.is_(False), KbDocument.owner_id == user_id)
        .order_by(KbDocument.id.desc())
    )
    doc_rows = all_docs_result.all()
    docs = [doc for doc, _file in doc_rows]
    doc_ids = [int(doc.id) for doc in docs]
    latest_tasks: dict[int, SystemTaskQueue] = {}
    if doc_ids:
        latest_task_ids = (
            select(func.max(SystemTaskQueue.id).label("id"))
            .where(
                SystemTaskQueue.module == "knowledge",
                SystemTaskQueue.task_type == PIPELINE_TASK_TYPE,
                SystemTaskQueue.document_id.in_(doc_ids),
            )
            .group_by(SystemTaskQueue.document_id)
            .subquery()
        )
        tasks = (await db.execute(
            select(SystemTaskQueue).join(latest_task_ids, SystemTaskQueue.id == latest_task_ids.c.id)
        )).scalars().all()
        latest_tasks = _latest_task_by_document(list(tasks))
    paused_stages, paused_lanes = _load_paused_worker_config()

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
    doc_progresses = []
    stuck_docs = []
    for d, file in doc_rows:
        source_available, source_state = _source_state(file)
        task = latest_tasks.get(int(d.id))
        task_status = _task_display_status(task, paused_stages, paused_lanes)
        statuses = _stage_statuses(d, task, task_status)
        bucket = _document_bucket(statuses, task, task_status, source_available=source_available)
        counters[bucket] += 1
        parse_error = str(d.parse_error or "")
        if parse_error in NON_CONTENT_FILE_REASONS:
            source_state = parse_error
        elif parse_error in SOURCE_UNAVAILABLE_REASONS and source_available:
            source_state = "available"
        entry = {
            "id": d.id, "filename": d.filename, "total_pages": d.total_pages,
            "raw_status": statuses["raw_status"], "fusion_status": statuses["fusion_status"],
            "profile_status": statuses["profile_status"], "graph_status": statuses["graph_status"],
            "relation_status": statuses["relation_status"],
            "parse_status": d.parse_status, "created_at": str(d.created_at or ""),
            "source_available": bool(source_available), "source_state": source_state,
            "pipeline_status": bucket,
            "task_status": task.status if task is not None else None,
            "task_stage": task.stage_key if task is not None else None,
        }
        doc_progresses.append(entry)
        if bucket in {"failed", "source_unavailable"}:
            stuck_docs.append(entry)

    total = len(docs)
    completed = counters["completed"]
    failed = counters["failed"]
    partial = counters["partial"]
    running = counters["running"]
    queued = counters["queued"]
    paused = counters["paused"]
    waiting = counters["waiting"]
    source_unavailable = counters["source_unavailable"]

    entity_count = (await db.execute(
        select(func.count(KbEntityDictionary.id)).where(KbEntityDictionary.owner_id == user_id)
    )).scalar() or 0

    relation_count = (await db.execute(
        select(func.count(KbGraphEdge.id)).where(KbGraphEdge.owner_id == user_id)
    )).scalar() or 0

    file_relation_count = (await db.execute(
        select(func.count(KbFileRelation.id)).where(KbFileRelation.owner_id == user_id)
    )).scalar() or 0

    duplicate_entities = 0
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
        "duplicate_entity_groups": [{"name": name, "count": cnt} for name, cnt in dup_groups],
        "entity_category_distribution": entity_category_distribution,
        "document_progresses": doc_progresses,
        "stuck_documents": stuck_docs,
        "recent_completions": recent_completions,
    }
