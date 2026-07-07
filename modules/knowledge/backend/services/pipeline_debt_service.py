"""Classification and guarded remediation for historical knowledge pipeline debt."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.models.file import File
from app.models.system import SystemTaskQueue
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbDocument, KbPipelineRun, KbPipelineStageRun
from .document_service import document_deep_pipeline_complete, mark_document_source_unavailable
from .source_file_state import SourceFileAvailability, classify_file_availability

FILE_NOT_FOUND_MARKER = "File not found"
DOC_NOT_FOUND_PATTERN = "Document % not found"
INVALID_IMAGE_CONTENT_MARKER = "Invalid or unsupported image content"
PARSER_EMPTY_MARKER = "Parser returned no content blocks"
TASK_RESULT_FAILED_MARKER = "Task result status=failed"
GREENLET_SPAWN_MARKER = "greenlet_spawn"
DOCUMENT_ALREADY_PARSING_MARKER = "Document is already parsing"
DOCUMENT_IR_ATTR_MARKER = "'DocumentIr' object has no attribute 'get'"
LIFECYCLE_ARCHIVE_CATEGORIES = {
    "doc_missing",
    "doc_deleted",
    "source_file_missing",
    "source_file_deleted",
    "source_storage_path_missing",
    "source_path_unsafe",
    "source_file_physical_missing",
}
PENDING_OBSOLETE_CATEGORIES = {
    "pending_doc_missing",
    "pending_doc_deleted",
    "pending_source_file_missing",
    "pending_source_file_deleted",
    "pending_source_storage_path_missing",
    "pending_source_path_unsafe",
    "pending_source_file_physical_missing",
}
RUNNING_OBSOLETE_CATEGORIES = {
    "running_doc_missing",
    "running_doc_deleted",
    "running_source_file_missing",
    "running_source_file_deleted",
    "running_source_storage_path_missing",
    "running_source_path_unsafe",
    "running_source_file_physical_missing",
}
RUNNING_REQUEUE_CATEGORIES = {"running_live_interrupted"}
RUNNING_COMPLETE_CATEGORIES = {"running_live_already_complete"}
RETRYABLE_CATEGORIES = {"file_row_live"}
ACTIVE_DOCUMENT_STATUSES = {"parsing", "indexing", "collecting", "running", "fusing"}
FAILED_DOCUMENT_STATUSES = {"error", "failed"}
PIPELINE_DEBT_ORDER_VALUES = {"newest", "oldest"}
PIPELINE_QUEUE_TASK_TYPES = ("kb_pipeline_stage", "kb_pipeline")


def _load_task_parameters(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _classify_task(
    doc: KbDocument | None,
    file: File | None,
    error_message: str | None,
) -> tuple[str, str, str | None, str]:
    error_family = _classify_error_family(error_message)
    if doc is None:
        return "doc_missing", "archive_obsolete", None, error_family
    if doc.deleted:
        return "doc_deleted", "archive_obsolete", None, error_family
    source_state = classify_file_availability(file)
    if not source_state.available:
        return source_state.reason, "archive_lifecycle_skip", source_state.reason, error_family
    if error_family == "parser_no_content_blocks":
        return "parser_no_content_blocks", "parser_quality_investigation", None, error_family
    if error_family == "task_result_failed":
        return "pipeline_subtask_failed", "pipeline_stage_investigation", None, error_family
    if error_family == "greenlet_spawn":
        return "async_context_error", "code_defect_investigation", None, error_family
    if error_family == "document_already_parsing":
        return "duplicate_or_stale_parse_lock", "reconcile_inflight_state", None, error_family
    if error_family == "document_ir_contract_error":
        return "content_ir_contract_error", "code_defect_investigation", None, error_family
    return "file_row_live", "retry_or_parser_investigation", None, error_family


def _classify_error_family(error_message: str | None) -> str:
    lowered = (error_message or "").lower()
    if FILE_NOT_FOUND_MARKER.lower() in lowered:
        return "file_not_found"
    if lowered.startswith("document ") and " not found" in lowered:
        return "document_not_found"
    if INVALID_IMAGE_CONTENT_MARKER.lower() in lowered:
        return "invalid_or_unsupported_image_content"
    if PARSER_EMPTY_MARKER.lower() in lowered:
        return "parser_no_content_blocks"
    if TASK_RESULT_FAILED_MARKER.lower() in lowered:
        return "task_result_failed"
    if GREENLET_SPAWN_MARKER.lower() in lowered:
        return "greenlet_spawn"
    if DOCUMENT_ALREADY_PARSING_MARKER.lower() in lowered:
        return "document_already_parsing"
    if DOCUMENT_IR_ATTR_MARKER.lower() in lowered:
        return "document_ir_contract_error"
    return "other"


def _classify_orphan_run(
    run: KbPipelineRun,
    doc: KbDocument | None,
    file: File | None,
) -> tuple[str, str, str | None]:
    if doc is None:
        return "orphan_run_doc_missing", "reconcile_archive_diagnostic", None
    if doc.deleted:
        return "orphan_run_doc_deleted", "reconcile_archive_diagnostic", None
    source_state = classify_file_availability(file)
    if not source_state.available:
        return f"orphan_run_{source_state.reason}", "reconcile_source_unavailable", source_state.reason
    return "orphan_run_live_without_task", "reconcile_stale_running_run", None


def _is_archiveable(category: str) -> bool:
    return category in LIFECYCLE_ARCHIVE_CATEGORIES


def _is_retryable(category: str) -> bool:
    return category in RETRYABLE_CATEGORIES


def _build_error_filter(error_marker: str | None):
    if error_marker:
        return SystemTaskQueue.error_message.ilike(f"%{error_marker}%")
    return or_(
        SystemTaskQueue.error_message.ilike(f"%{FILE_NOT_FOUND_MARKER}%"),
        SystemTaskQueue.error_message.ilike(DOC_NOT_FOUND_PATTERN),
        SystemTaskQueue.error_message.ilike(f"%{INVALID_IMAGE_CONTENT_MARKER}%"),
        SystemTaskQueue.error_message.ilike(f"%{PARSER_EMPTY_MARKER}%"),
        SystemTaskQueue.error_message.ilike(f"%{TASK_RESULT_FAILED_MARKER}%"),
        SystemTaskQueue.error_message.ilike(f"%{GREENLET_SPAWN_MARKER}%"),
        SystemTaskQueue.error_message.ilike(f"%{DOCUMENT_ALREADY_PARSING_MARKER}%"),
        SystemTaskQueue.error_message.ilike(f"%{DOCUMENT_IR_ATTR_MARKER}%"),
    )


async def _load_candidate_tasks(
    db: AsyncSession,
    *,
    limit: int = 500,
    error_marker: str | None = None,
    task_ids: list[int] | None = None,
    order: str = "newest",
) -> list[SystemTaskQueue]:
    error_filter = _build_error_filter(error_marker)
    filters = [
        SystemTaskQueue.module == "knowledge",
        SystemTaskQueue.task_type.in_(PIPELINE_QUEUE_TASK_TYPES),
        SystemTaskQueue.status == "failed",
        error_filter,
    ]
    if task_ids:
        filters.append(SystemTaskQueue.id.in_(task_ids))
    order_by = SystemTaskQueue.id.asc() if order == "oldest" else SystemTaskQueue.id.desc()
    query = select(SystemTaskQueue).where(*filters).order_by(order_by)
    if not task_ids:
        query = query.limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def _load_pending_pipeline_tasks(
    db: AsyncSession,
    *,
    limit: int = 500,
    task_ids: list[int] | None = None,
    order: str = "oldest",
) -> list[SystemTaskQueue]:
    filters = [
        SystemTaskQueue.module == "knowledge",
        SystemTaskQueue.task_type.in_(PIPELINE_QUEUE_TASK_TYPES),
        SystemTaskQueue.status == "pending",
    ]
    if task_ids:
        filters.append(SystemTaskQueue.id.in_(task_ids))
    order_by = SystemTaskQueue.id.desc() if order == "newest" else SystemTaskQueue.id.asc()
    query = select(SystemTaskQueue).where(*filters).order_by(order_by)
    if not task_ids:
        query = query.limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def _load_running_pipeline_tasks(
    db: AsyncSession,
    *,
    limit: int = 500,
    task_ids: list[int] | None = None,
    order: str = "oldest",
) -> list[SystemTaskQueue]:
    filters = [
        SystemTaskQueue.module == "knowledge",
        SystemTaskQueue.task_type.in_(PIPELINE_QUEUE_TASK_TYPES),
        SystemTaskQueue.status == "running",
    ]
    if task_ids:
        filters.append(SystemTaskQueue.id.in_(task_ids))
    order_by = SystemTaskQueue.id.desc() if order == "newest" else SystemTaskQueue.id.asc()
    query = select(SystemTaskQueue).where(*filters).order_by(order_by)
    if not task_ids:
        query = query.limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


def _classify_pending_task(
    doc: KbDocument | None,
    file: File | None,
) -> tuple[str, str, str | None, SourceFileAvailability | None]:
    if doc is None:
        return "pending_doc_missing", "archive_pending_obsolete", None, None
    if doc.deleted:
        return "pending_doc_deleted", "archive_pending_obsolete", None, None
    source_state = classify_file_availability(file)
    if not source_state.available:
        return f"pending_{source_state.reason}", "archive_pending_obsolete", source_state.reason, source_state
    return "pending_live", "keep_pending", None, source_state


def _classify_running_task(
    doc: KbDocument | None,
    file: File | None,
) -> tuple[str, str, str | None, SourceFileAvailability | None]:
    if doc is None:
        return "running_doc_missing", "archive_running_obsolete", None, None
    if doc.deleted:
        return "running_doc_deleted", "archive_running_obsolete", None, None
    source_state = classify_file_availability(file)
    if not source_state.available:
        return f"running_{source_state.reason}", "archive_running_obsolete", source_state.reason, source_state
    if document_deep_pipeline_complete(doc, source_available=True):
        return "running_live_already_complete", "archive_running_already_complete", None, source_state
    return "running_live_interrupted", "release_for_retry", None, source_state


def _normalize_category_tokens(values: list[str] | None) -> list[str]:
    categories: list[str] = []
    for raw in values or []:
        for part in str(raw).split(","):
            category = part.strip()
            if category and category not in categories:
                categories.append(category)
    return categories


def _normalize_category_limits(raw_limits: dict[str, int] | None) -> dict[str, int]:
    limits: dict[str, int] = {}
    for raw_category, raw_limit in (raw_limits or {}).items():
        category = str(raw_category).strip()
        if not category:
            continue
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            continue
        if limit > 0:
            limits[category] = limit
    return limits


def _select_items_by_category(
    items: list[dict[str, Any]],
    *,
    categories: list[str] | None = None,
    category_limits: dict[str, int] | None = None,
    limit_each: int | None = None,
    precise_task_ids: bool = False,
) -> dict[str, Any]:
    """Select classified rows with stable per-category limits.

    Explicit task_ids are an exact mode: callers already narrowed the SQL query,
    so category limits must not silently drop requested rows.
    """
    normalized_categories = _normalize_category_tokens(categories)
    normalized_limits = _normalize_category_limits(category_limits)
    normalized_limit_each = int(limit_each) if limit_each is not None else None
    if normalized_limit_each is not None and normalized_limit_each <= 0:
        normalized_limit_each = None

    if precise_task_ids:
        return {
            "applied": False,
            "mode": "task_ids",
            "categories": [],
            "category_limits": {},
            "limit_each": normalized_limit_each,
            "selected_items": list(items),
            "not_selected_items": [],
            "selected_by_category": _count_by_category(items),
            "not_selected_by_category": {},
        }

    if not normalized_categories and not normalized_limits and normalized_limit_each is None:
        return {
            "applied": False,
            "mode": "all",
            "categories": [],
            "category_limits": {},
            "limit_each": None,
            "selected_items": list(items),
            "not_selected_items": [],
            "selected_by_category": _count_by_category(items),
            "not_selected_by_category": {},
        }

    requested_categories = list(normalized_categories)
    for category in normalized_limits:
        if category not in requested_categories:
            requested_categories.append(category)
    if not requested_categories:
        for item in items:
            category = str(item["category"])
            if category not in requested_categories:
                requested_categories.append(category)

    requested_set = set(requested_categories)
    selected: list[dict[str, Any]] = []
    not_selected: list[dict[str, Any]] = []
    selected_counts: Counter[str] = Counter()

    for item in items:
        category = str(item["category"])
        if category not in requested_set:
            not_selected.append({**item, "not_selected_reason": "category_not_requested"})
            continue
        category_limit = normalized_limits.get(category, normalized_limit_each)
        if category_limit is not None and selected_counts[category] >= category_limit:
            not_selected.append({**item, "not_selected_reason": "category_limit_reached"})
            continue
        selected.append(item)
        selected_counts[category] += 1

    return {
        "applied": True,
        "mode": "category_selection",
        "categories": requested_categories,
        "category_limits": normalized_limits,
        "limit_each": normalized_limit_each,
        "selected_items": selected,
        "not_selected_items": not_selected,
        "selected_by_category": dict(selected_counts),
        "not_selected_by_category": _count_by_category(not_selected),
    }


async def _classify_tasks(db: AsyncSession, tasks: list[SystemTaskQueue]) -> dict:
    items: list[dict[str, Any]] = []
    summary: Counter[str] = Counter()
    error_summary: Counter[str] = Counter()

    for task in tasks:
        params = _load_task_parameters(task.parameters)
        document_id = int(params.get("document_id", 0) or 0)
        doc = await db.get(KbDocument, document_id) if document_id > 0 else None
        file = await db.get(File, doc.file_id) if doc is not None else None
        source_state = classify_file_availability(file) if doc is not None else None
        category, suggested_action, parse_error, error_family = _classify_task(doc, file, task.error_message)
        summary[category] += 1
        error_summary[error_family] += 1
        item = {
            "task_id": task.id,
            "document_id": document_id or None,
            "file_id": doc.file_id if doc is not None else None,
            "storage_path": source_state.storage_path if source_state is not None else None,
            "physical_path": source_state.physical_path if source_state is not None else None,
            "category": category,
            "error_family": error_family,
            "suggested_action": suggested_action,
            "archiveable": _is_archiveable(category),
            "retryable": _is_retryable(category),
            "would_set_parse_error": parse_error,
            "queue_status": task.status,
            "error_message": task.error_message,
        }
        items.append(item)

    return {
        "dry_run": True,
        "matched": len(items),
        "summary": dict(summary),
        "error_summary": dict(error_summary),
        "items": items,
    }


async def _classify_pending_tasks(db: AsyncSession, tasks: list[SystemTaskQueue]) -> dict:
    items: list[dict[str, Any]] = []
    summary: Counter[str] = Counter()

    for task in tasks:
        params = _load_task_parameters(task.parameters)
        document_id = int(params.get("document_id", 0) or 0)
        doc = await db.get(KbDocument, document_id) if document_id > 0 else None
        file = await db.get(File, doc.file_id) if doc is not None else None
        category, suggested_action, parse_error, source_state = _classify_pending_task(doc, file)
        summary[category] += 1
        items.append({
            "task_id": task.id,
            "document_id": document_id or None,
            "file_id": doc.file_id if doc is not None else None,
            "storage_path": source_state.storage_path if source_state is not None else None,
            "physical_path": source_state.physical_path if source_state is not None else None,
            "category": category,
            "suggested_action": suggested_action,
            "archiveable": category in PENDING_OBSOLETE_CATEGORIES,
            "would_set_parse_error": parse_error,
            "queue_status": task.status,
            "created_at": task.created_at.isoformat() if getattr(task, "created_at", None) else None,
            "updated_at": task.updated_at.isoformat() if getattr(task, "updated_at", None) else None,
        })

    return {
        "dry_run": True,
        "matched": len(items),
        "summary": dict(summary),
        "items": items,
    }


async def _classify_running_tasks(db: AsyncSession, tasks: list[SystemTaskQueue]) -> dict:
    items: list[dict[str, Any]] = []
    summary: Counter[str] = Counter()

    for task in tasks:
        params = _load_task_parameters(task.parameters)
        document_id = int(params.get("document_id", 0) or 0)
        doc = await db.get(KbDocument, document_id) if document_id > 0 else None
        file = await db.get(File, doc.file_id) if doc is not None else None
        category, suggested_action, parse_error, source_state = _classify_running_task(doc, file)
        summary[category] += 1
        items.append({
            "task_id": task.id,
            "document_id": document_id or None,
            "file_id": doc.file_id if doc is not None else None,
            "storage_path": source_state.storage_path if source_state is not None else None,
            "physical_path": source_state.physical_path if source_state is not None else None,
            "category": category,
            "suggested_action": suggested_action,
            "archiveable": category in RUNNING_OBSOLETE_CATEGORIES | RUNNING_COMPLETE_CATEGORIES,
            "requeueable": category in RUNNING_REQUEUE_CATEGORIES,
            "would_set_parse_error": parse_error,
            "queue_status": task.status,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "started_at": task.started_at.isoformat() if getattr(task, "started_at", None) else None,
            "updated_at": task.updated_at.isoformat() if getattr(task, "updated_at", None) else None,
        })

    return {
        "dry_run": True,
        "matched": len(items),
        "summary": dict(summary),
        "items": items,
    }


async def _classify_orphan_running_runs(db: AsyncSession) -> dict:
    result = await db.execute(
        select(KbPipelineRun)
        .where(
            KbPipelineRun.status == "running",
            KbPipelineRun.task_id.is_(None),
        )
        .order_by(KbPipelineRun.id.asc())
    )
    runs = [
        run
        for run in result.scalars().all()
        if hasattr(run, "task_id") and hasattr(run, "document_id") and hasattr(run, "file_id")
    ]
    if not runs:
        return {
            "dry_run": True,
            "matched": 0,
            "summary": {},
            "items": [],
            "requires_reconcile": False,
        }

    run_ids = [int(run.id) for run in runs]
    stage_result = await db.execute(
        select(KbPipelineStageRun)
        .where(KbPipelineStageRun.run_id.in_(run_ids))
        .order_by(KbPipelineStageRun.run_id.asc(), KbPipelineStageRun.id.asc())
    )
    stages_by_run: dict[int, list[KbPipelineStageRun]] = {}
    for stage in stage_result.scalars().all():
        stages_by_run.setdefault(int(stage.run_id or 0), []).append(stage)

    items: list[dict[str, Any]] = []
    summary: Counter[str] = Counter()
    for run in runs:
        doc = await db.get(KbDocument, run.document_id)
        file = await db.get(File, run.file_id)
        category, suggested_action, parse_error = _classify_orphan_run(run, doc, file)
        summary[category] += 1
        stages = stages_by_run.get(int(run.id), [])
        latest_stage = stages[-1] if stages else None
        items.append({
            "run_id": run.id,
            "document_id": run.document_id,
            "file_id": run.file_id,
            "category": category,
            "suggested_action": suggested_action,
            "would_set_parse_error": parse_error,
            "run_status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            "stage_count": len(stages),
            "latest_stage": latest_stage.stage if latest_stage else None,
            "latest_stage_status": latest_stage.status if latest_stage else None,
            "latest_stage_reason": latest_stage.reason if latest_stage else None,
        })

    return {
        "dry_run": True,
        "matched": len(items),
        "summary": dict(summary),
        "items": items,
        "requires_reconcile": True,
        "note": "Diagnostic only: orphan running rows have no queue task_id and are not mutated by pipeline debt apply.",
    }


async def _audit_document_status_machine(db: AsyncSession, *, sample_limit: int = 20) -> dict:
    result = await db.execute(
        select(KbDocument, File)
        .outerjoin(File, File.id == KbDocument.file_id)
        .where(KbDocument.deleted.is_(False))
        .order_by(KbDocument.id.desc())
    )
    summary: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    seen_samples: Counter[str] = Counter()

    for row in result.all():
        if not isinstance(row, tuple | list) or len(row) != 2:
            continue
        doc, file = row
        stage_statuses = {
            "parse": doc.parse_status or "pending",
            "vector": doc.vector_status or "pending",
            "raw": getattr(doc, "raw_status", "pending") or "pending",
            "fusion": getattr(doc, "fusion_status", "pending") or "pending",
            "profile": getattr(doc, "profile_status", "pending") or "pending",
            "graph": getattr(doc, "graph_status", "pending") or "pending",
            "relation": getattr(doc, "relation_status", "pending") or "pending",
        }

        category: str | None = None
        if file is None:
            category = "status_doc_source_file_missing"
        elif file.deleted:
            category = "status_doc_source_file_deleted"
        elif any(status in FAILED_DOCUMENT_STATUSES for status in stage_statuses.values()):
            category = "status_doc_failed_stage"
        elif any(status in ACTIVE_DOCUMENT_STATUSES for status in stage_statuses.values()):
            category = "status_doc_active_without_live_queue_check"

        if category is None:
            continue

        summary[category] += 1
        if seen_samples[category] >= sample_limit:
            continue
        seen_samples[category] += 1
        items.append({
            "document_id": doc.id,
            "file_id": doc.file_id,
            "category": category,
            "parse_error": doc.parse_error,
            "stage_statuses": stage_statuses,
            "source_file_exists": file is not None,
            "source_file_deleted": bool(file.deleted) if file is not None else None,
            "suggested_action": (
                "mark_source_unavailable_or_restore_source"
                if category.startswith("status_doc_source_file_")
                else "inspect_or_retry_pipeline"
            ),
        })

    return {
        "dry_run": True,
        "matched": sum(summary.values()),
        "summary": dict(summary),
        "items": items,
        "sample_limit_per_category": sample_limit,
    }


def _build_problem_queue(
    classification: dict,
    orphan_running_runs: dict,
    status_machine_audit: dict,
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []

    for category, count in classification.get("summary", {}).items():
        severity = "P1" if category in {
            "pipeline_subtask_failed",
            "async_context_error",
            "duplicate_or_stale_parse_lock",
            "content_ir_contract_error",
        } else "P2"
        queue.append({
            "source": "framework_system_task_queues",
            "category": category,
            "count": count,
            "severity": severity,
            "next_action": "inspect_or_apply_guarded_pipeline_debt_action",
        })

    for category, count in orphan_running_runs.get("summary", {}).items():
        queue.append({
            "source": "kb_pipeline_runs",
            "category": category,
            "count": count,
            "severity": "P1",
            "next_action": "reconcile_diagnostic_run_state",
        })

    for category, count in status_machine_audit.get("summary", {}).items():
        queue.append({
            "source": "kb_documents",
            "category": category,
            "count": count,
            "severity": "P1" if category.startswith("status_doc_source_file_") else "P2",
            "next_action": "repair_document_status_or_retry_pipeline",
        })

    severity_rank = {"P1": 0, "P2": 1, "P3": 2}
    return sorted(
        queue,
        key=lambda item: (
            severity_rank.get(str(item["severity"]), 9),
            -int(item["count"]),
            str(item["category"]),
        ),
    )


async def classify_pipeline_lifecycle_debt(
    db: AsyncSession,
    *,
    limit: int = 500,
    error_marker: str | None = None,
    task_ids: list[int] | None = None,
    categories: list[str] | None = None,
    category_limits: dict[str, int] | None = None,
    limit_each: int | None = None,
    order: str = "newest",
) -> dict:
    """Classify knowledge pipeline queue debt without mutating queue rows."""
    tasks = await _load_candidate_tasks(
        db,
        limit=limit,
        error_marker=error_marker,
        task_ids=task_ids,
        order=order,
    )
    classification = await _classify_tasks(db, tasks)
    selection = _select_items_by_category(
        classification["items"],
        categories=categories,
        category_limits=category_limits,
        limit_each=limit_each,
        precise_task_ids=bool(task_ids),
    )
    orphan_running_runs = await _classify_orphan_running_runs(db)
    status_machine_audit = await _audit_document_status_machine(db)
    classification["order"] = order if order in PIPELINE_DEBT_ORDER_VALUES else "newest"
    classification["selected"] = len(selection["selected_items"])
    classification["not_selected"] = len(selection["not_selected_items"])
    classification["selected_by_category"] = selection["selected_by_category"]
    classification["not_selected_by_category"] = selection["not_selected_by_category"]
    classification["selected_items"] = selection["selected_items"]
    classification["not_selected_items"] = selection["not_selected_items"]
    classification["selection"] = {
        "applied": selection["applied"],
        "mode": selection["mode"],
        "categories": selection["categories"],
        "category_limits": selection["category_limits"],
        "limit_each": selection["limit_each"],
    }
    classification["orphan_running_runs"] = orphan_running_runs
    classification["status_machine_audit"] = status_machine_audit
    classification["problem_queue"] = _build_problem_queue(
        classification,
        orphan_running_runs,
        status_machine_audit,
    )
    return classification


async def reconcile_pending_pipeline_queue(
    db: AsyncSession,
    *,
    limit: int = 500,
    task_ids: list[int] | None = None,
    dry_run: bool = True,
    categories: list[str] | None = None,
    category_limits: dict[str, int] | None = None,
    limit_each: int | None = None,
    order: str = "oldest",
) -> dict:
    """Dry-run or archive obsolete pending knowledge pipeline queue rows.

    Live pending rows are never mutated. This covers current ``kb_pipeline_stage``
    tasks and legacy ``kb_pipeline`` rows left from earlier imports/reloads.
    """
    tasks = await _load_pending_pipeline_tasks(
        db,
        limit=max(1, min(int(limit or 500), 5000)),
        task_ids=task_ids,
        order=order,
    )
    classification = await _classify_pending_tasks(db, tasks)
    selection = _select_items_by_category(
        classification["items"],
        categories=categories,
        category_limits=category_limits,
        limit_each=limit_each,
        precise_task_ids=bool(task_ids),
    )
    selected_items = selection["selected_items"]
    selected_obsolete = [
        item for item in selected_items
        if str(item.get("category")) in PENDING_OBSOLETE_CATEGORIES
    ]
    skipped_live = len(selected_items) - len(selected_obsolete)
    result = {
        **classification,
        "dry_run": dry_run,
        "will_mutate": not dry_run,
        "order": order if order in PIPELINE_DEBT_ORDER_VALUES else "oldest",
        "selected": len(selected_items),
        "selected_obsolete": len(selected_obsolete),
        "skipped_live": skipped_live,
        "not_selected": len(selection["not_selected_items"]),
        "selected_by_category": selection["selected_by_category"],
        "not_selected_by_category": selection["not_selected_by_category"],
        "selected_items": selected_items,
        "not_selected_items": selection["not_selected_items"],
        "selection": {
            "applied": selection["applied"],
            "mode": selection["mode"],
            "categories": selection["categories"],
            "category_limits": selection["category_limits"],
            "limit_each": selection["limit_each"],
        },
        "changed": 0,
    }
    if dry_run or not selected_obsolete:
        return result

    tasks_by_id = {int(task.id): task for task in tasks}
    now = datetime.now(timezone.utc)
    for item in selected_obsolete:
        task = tasks_by_id.get(int(item["task_id"]))
        if task is None or task.status != "pending":
            continue
        _archive_task(task, item, now)
        if item.get("would_set_parse_error"):
            await _mark_document_for_archived_lifecycle_debt(db, item)
        result["changed"] += 1

    await db.commit()
    result["dry_run"] = False
    result["will_mutate"] = True
    return result


def _count_by_category(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(item["category"]) for item in items))


def _archive_task(task: SystemTaskQueue, item: dict[str, Any], now: datetime) -> None:
    previous_error = task.error_message
    previous_status = task.status
    previous_result = task.result
    task.status = "completed"
    task.completed_at = now
    task.started_at = None
    task.error_message = None
    task.result = json.dumps({
        "status": "skipped",
        "archived_by": "knowledge_pipeline_debt_governance",
        "classification": item["category"],
        "reason": item["would_set_parse_error"] or item["category"],
        "document_id": item["document_id"],
        "file_id": item["file_id"],
        "previous_error_message": previous_error,
        "previous_status": previous_status,
        "previous_result": previous_result,
    }, ensure_ascii=False)


def _retry_task(task: SystemTaskQueue, item: dict[str, Any]) -> None:
    previous_error = task.error_message
    task.status = "pending"
    task.retry_count = 0
    task.started_at = None
    task.completed_at = None
    task.error_message = None
    task.result = json.dumps({
        "status": "requeued",
        "requeued_by": "knowledge_pipeline_debt_governance",
        "classification": item["category"],
        "document_id": item["document_id"],
        "file_id": item["file_id"],
        "previous_error_message": previous_error,
    }, ensure_ascii=False)


def _release_running_task(task: SystemTaskQueue, item: dict[str, Any]) -> None:
    previous_error = task.error_message
    task.status = "pending"
    task.started_at = None
    task.completed_at = None
    task.error_message = None
    task.result = json.dumps({
        "status": "requeued",
        "requeued_by": "knowledge_running_pipeline_queue_reconcile",
        "classification": item["category"],
        "document_id": item["document_id"],
        "file_id": item["file_id"],
        "previous_error_message": previous_error,
    }, ensure_ascii=False)


async def _close_running_pipeline_diagnostics(
    db: AsyncSession,
    item: dict[str, Any],
    now: datetime,
    *,
    reason: str,
) -> int:
    task_id = int(item.get("task_id") or 0)
    document_id = int(item.get("document_id") or 0)
    if task_id <= 0:
        return 0

    result = await db.execute(
        select(KbPipelineRun)
        .where(
            KbPipelineRun.task_id == task_id,
            KbPipelineRun.status == "running",
        )
        .order_by(KbPipelineRun.id.asc())
    )
    runs = list(result.scalars().all())
    if not runs:
        return 0

    run_ids = [int(run.id) for run in runs]
    stage_result = await db.execute(
        select(KbPipelineStageRun)
        .where(
            KbPipelineStageRun.run_id.in_(run_ids),
            KbPipelineStageRun.status == "running",
        )
    )
    for stage in stage_result.scalars().all():
        stage.status = "skipped"
        stage.reason = reason
        stage.error_message = "Interrupted queue task reconciled before completion"
        stage.completed_at = now
        if stage.started_at and not stage.duration_ms:
            stage.duration_ms = int((now - stage.started_at).total_seconds() * 1000)

    for run in runs:
        previous = run.diagnostics_json
        merged: dict[str, Any] = dict(previous) if isinstance(previous, dict) else {}
        merged.update({
            "previous_status": run.status,
            "previous_reason": run.reason,
            "previous_diagnostics": previous,
            "reconciled_by": "knowledge_running_pipeline_queue_reconcile",
            "reconciled_at": now.isoformat(),
            "reconcile_category": item["category"],
            "reconcile_reason": reason,
            "task_id": task_id,
            "document_id": document_id or run.document_id,
        })
        run.diagnostics_json = merged
        run.status = "skipped"
        run.reason = reason
        run.completed_at = now
    return len(runs)


async def _mark_document_for_archived_lifecycle_debt(
    db: AsyncSession,
    item: dict[str, Any],
) -> None:
    reason = item.get("would_set_parse_error")
    document_id = int(item.get("document_id") or 0)
    if not reason or document_id <= 0:
        return
    doc = await db.get(KbDocument, document_id)
    if doc is None or doc.deleted:
        return
    mark_document_source_unavailable(doc, str(reason))


async def apply_pipeline_lifecycle_debt_action(
    db: AsyncSession,
    *,
    action: str,
    limit: int = 500,
    task_ids: list[int] | None = None,
    dry_run: bool = True,
    categories: list[str] | None = None,
    category_limits: dict[str, int] | None = None,
    limit_each: int | None = None,
    order: str = "newest",
) -> dict:
    """Apply a guarded governance action to classified historical debt.

    ``archive_obsolete`` only converts lifecycle-obsolete rows to completed
    skipped results. ``retry_live`` only requeues rows whose framework file row
    is still live. Parser quality debt is intentionally never auto-mutated.
    """
    if action not in {"archive_obsolete", "retry_live"}:
        raise ValueError("Unsupported pipeline debt action")

    tasks = await _load_candidate_tasks(db, limit=limit, task_ids=task_ids, order=order)
    classification = await _classify_tasks(db, tasks)
    selection = _select_items_by_category(
        classification["items"],
        categories=categories,
        category_limits=category_limits,
        limit_each=limit_each,
        precise_task_ids=bool(task_ids),
    )
    tasks_by_id = {int(task.id): task for task in tasks}
    changed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for item in selection["selected_items"]:
        task = tasks_by_id.get(int(item["task_id"]))
        if task is None:
            continue
        if action == "archive_obsolete" and item["archiveable"]:
            changed.append(item)
            if not dry_run:
                await _mark_document_for_archived_lifecycle_debt(db, item)
                _archive_task(task, item, now)
        elif action == "retry_live" and item["retryable"]:
            changed.append(item)
            if not dry_run:
                _retry_task(task, item)
        else:
            skipped.append({
                **item,
                "skip_reason": "action_not_allowed_for_category",
            })

    if not dry_run and changed:
        await db.commit()

    return {
        "dry_run": dry_run,
        "action": action,
        "order": order if order in PIPELINE_DEBT_ORDER_VALUES else "newest",
        "matched": classification["matched"],
        "selected": len(selection["selected_items"]),
        "not_selected": len(selection["not_selected_items"]),
        "changed": len(changed),
        "skipped": len(skipped),
        "summary": classification["summary"],
        "selected_by_category": selection["selected_by_category"],
        "not_selected_by_category": selection["not_selected_by_category"],
        "changed_by_category": _count_by_category(changed),
        "skipped_by_category": _count_by_category(skipped),
        "changed_items": changed,
        "skipped_items": skipped,
        "not_selected_items": selection["not_selected_items"],
        "selection": {
            "applied": selection["applied"],
            "mode": selection["mode"],
            "categories": selection["categories"],
            "category_limits": selection["category_limits"],
            "limit_each": selection["limit_each"],
        },
    }


async def reconcile_running_pipeline_queue(
    db: AsyncSession,
    *,
    limit: int = 500,
    task_ids: list[int] | None = None,
    dry_run: bool = True,
    categories: list[str] | None = None,
    category_limits: dict[str, int] | None = None,
    limit_each: int | None = None,
    order: str = "oldest",
) -> dict:
    """Dry-run or recover interrupted running knowledge pipeline queue rows.

    Live rows are released back to ``pending`` so the worker can retry from
    persisted stage outputs. Obsolete rows are completed as skipped. This covers
    current ``kb_pipeline_stage`` tasks and legacy ``kb_pipeline`` rows without
    requiring a full document rerun by hand.
    """
    tasks = await _load_running_pipeline_tasks(
        db,
        limit=max(1, min(int(limit or 500), 5000)),
        task_ids=task_ids,
        order=order,
    )
    classification = await _classify_running_tasks(db, tasks)
    selection = _select_items_by_category(
        classification["items"],
        categories=categories,
        category_limits=category_limits,
        limit_each=limit_each,
        precise_task_ids=bool(task_ids),
    )
    selected_items = selection["selected_items"]
    selected_requeue = [
        item for item in selected_items
        if str(item.get("category")) in RUNNING_REQUEUE_CATEGORIES
    ]
    selected_obsolete = [
        item for item in selected_items
        if str(item.get("category")) in RUNNING_OBSOLETE_CATEGORIES
    ]
    selected_complete = [
        item for item in selected_items
        if str(item.get("category")) in RUNNING_COMPLETE_CATEGORIES
    ]
    skipped_unhandled = (
        len(selected_items)
        - len(selected_requeue)
        - len(selected_obsolete)
        - len(selected_complete)
    )
    result = {
        **classification,
        "dry_run": dry_run,
        "will_mutate": not dry_run,
        "order": order if order in PIPELINE_DEBT_ORDER_VALUES else "oldest",
        "selected": len(selected_items),
        "selected_requeue": len(selected_requeue),
        "selected_obsolete": len(selected_obsolete),
        "selected_complete": len(selected_complete),
        "skipped_unhandled": skipped_unhandled,
        "not_selected": len(selection["not_selected_items"]),
        "selected_by_category": selection["selected_by_category"],
        "not_selected_by_category": selection["not_selected_by_category"],
        "selected_items": selected_items,
        "not_selected_items": selection["not_selected_items"],
        "selection": {
            "applied": selection["applied"],
            "mode": selection["mode"],
            "categories": selection["categories"],
            "category_limits": selection["category_limits"],
            "limit_each": selection["limit_each"],
        },
        "changed": 0,
        "closed_runs": 0,
    }
    if dry_run:
        return result

    tasks_by_id = {int(task.id): task for task in tasks}
    now = datetime.now(timezone.utc)
    for item in selected_requeue:
        task = tasks_by_id.get(int(item["task_id"]))
        if task is None or task.status != "running":
            continue
        result["closed_runs"] += await _close_running_pipeline_diagnostics(
            db,
            item,
            now,
            reason="queue_released_for_retry",
        )
        _release_running_task(task, item)
        result["changed"] += 1

    for item in selected_obsolete:
        task = tasks_by_id.get(int(item["task_id"]))
        if task is None or task.status != "running":
            continue
        result["closed_runs"] += await _close_running_pipeline_diagnostics(
            db,
            item,
            now,
            reason=str(item.get("would_set_parse_error") or item["category"]),
        )
        _archive_task(task, item, now)
        if item.get("would_set_parse_error"):
            await _mark_document_for_archived_lifecycle_debt(db, item)
        result["changed"] += 1

    for item in selected_complete:
        task = tasks_by_id.get(int(item["task_id"]))
        if task is None or task.status != "running":
            continue
        result["closed_runs"] += await _close_running_pipeline_diagnostics(
            db,
            item,
            now,
            reason="already_complete",
        )
        _archive_task(task, item, now)
        result["changed"] += 1

    if result["changed"]:
        await db.commit()
    result["dry_run"] = False
    result["will_mutate"] = True
    return result
