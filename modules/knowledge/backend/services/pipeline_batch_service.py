"""Guarded single-stage batch enqueue for Knowledge administrators."""
from __future__ import annotations

from collections import Counter
from typing import Any

from app.core.exceptions import ValidationError
from app.models.file import File
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbDocument
from .page_asset_service import page_assets_complete
from .pipeline_service import (
    VISUAL_EXTENSIONS,
    _raw_round_complete,
    _ready_for_fusion,
    enqueue_pipeline_stage_task,
)
from .source_file_state import classify_file_availability

ALLOWED_BATCH_STAGES = {"raw_ocr", "raw_vision", "fusion"}
CONFIRM_ENQUEUE_PIPELINE_STAGE_BATCH = "ENQUEUE_KNOWLEDGE_STAGE_BATCH"
MAX_BATCH_LIMIT = 500


def _normalize_extensions(extensions: list[str] | None) -> list[str]:
    return sorted({str(item).strip().lower().lstrip(".") for item in (extensions or []) if str(item).strip()})


def _document_item(doc: KbDocument, *, reason: str = "eligible") -> dict[str, Any]:
    return {
        "document_id": int(doc.id),
        "owner_id": int(doc.owner_id),
        "file_id": int(doc.file_id),
        "filename": doc.filename,
        "extension": doc.extension,
        "total_pages": int(doc.total_pages or 0),
        "reason": reason,
        "stage_statuses": {
            "parse": doc.parse_status,
            "raw": doc.raw_status,
            "fusion": doc.fusion_status,
            "profile": getattr(doc, "profile_status", "pending"),
            "graph": getattr(doc, "graph_status", "pending"),
            "relation": getattr(doc, "relation_status", "pending"),
        },
    }


async def _stage_eligibility(
    db: AsyncSession,
    doc: KbDocument,
    file: File | None,
    stage: str,
) -> str:
    source_state = classify_file_availability(file)
    if not source_state.available:
        return source_state.reason

    extension = str(doc.extension or "").lower().lstrip(".")
    if stage in {"raw_ocr", "raw_vision"}:
        if extension not in VISUAL_EXTENSIONS:
            return "non_visual_document"
        if not await page_assets_complete(
            db,
            document_id=int(doc.id),
            total_pages=int(doc.total_pages or 1),
        ):
            return "page_assets_incomplete"
        round_num = 2 if stage == "raw_ocr" else 3
        if await _raw_round_complete(db, doc, round_num):
            return "stage_already_complete"
        return "eligible"

    if str(doc.fusion_status or "pending").lower() == "done":
        return "stage_already_complete"
    if not await _ready_for_fusion(db, doc, allow_degraded_parse=True):
        return "upstream_not_ready"
    return "eligible"


async def enqueue_pipeline_stage_batch(
    db: AsyncSession,
    *,
    actor_id: int,
    owner_id: int,
    stage: str,
    dry_run: bool = True,
    confirm: str = "",
    audit_reason: str = "",
    limit: int = 20,
    document_ids: list[int] | None = None,
    extensions: list[str] | None = None,
    filename_contains: str = "",
    priority: int = 5,
) -> dict[str, Any]:
    """Preview or enqueue one bounded stage without publishing DAG successors."""
    normalized_stage = str(stage or "").strip().lower()
    if normalized_stage not in ALLOWED_BATCH_STAGES:
        raise ValidationError("stage must be one of raw_ocr, raw_vision, or fusion")
    if int(owner_id or 0) <= 0:
        raise ValidationError("owner_id must be positive")
    if not dry_run and confirm != CONFIRM_ENQUEUE_PIPELINE_STAGE_BATCH:
        raise ValidationError(
            f"confirm must be {CONFIRM_ENQUEUE_PIPELINE_STAGE_BATCH} to enqueue a stage batch"
        )

    bounded_limit = max(1, min(int(limit or 20), MAX_BATCH_LIMIT))
    bounded_priority = max(0, min(int(priority or 0), 100))
    normalized_extensions = _normalize_extensions(extensions)
    exact_ids = sorted({int(item) for item in (document_ids or []) if int(item) > 0})
    filename_filter = str(filename_contains or "").strip()
    scan_limit = min(max(bounded_limit * 10, 100), 5000)

    filters = [
        KbDocument.owner_id == int(owner_id),
        KbDocument.deleted.is_(False),
    ]
    if exact_ids:
        filters.append(KbDocument.id.in_(exact_ids))
        scan_limit = min(max(len(exact_ids), bounded_limit), 5000)
    if normalized_extensions:
        filters.append(func.lower(KbDocument.extension).in_(normalized_extensions))
    if filename_filter:
        filters.append(KbDocument.filename.ilike(f"%{filename_filter}%"))

    result = await db.execute(
        select(KbDocument, File)
        .outerjoin(File, File.id == KbDocument.file_id)
        .where(*filters)
        .order_by(KbDocument.total_pages.asc(), KbDocument.id.desc())
        .limit(scan_limit)
    )
    rows = result.all()

    selected: list[KbDocument] = []
    candidate_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    skipped_by_reason: Counter[str] = Counter()
    for doc, file in rows:
        reason = await _stage_eligibility(db, doc, file, normalized_stage)
        item = _document_item(doc, reason=reason)
        if reason == "eligible" and len(selected) < bounded_limit:
            selected.append(doc)
            candidate_items.append(item)
        else:
            if reason == "eligible":
                reason = "batch_limit_reached"
                item["reason"] = reason
            skipped_by_reason[reason] += 1
            skipped_items.append(item)

    base = {
        "action": "enqueue_pipeline_stage_batch",
        "dry_run": bool(dry_run),
        "actor_id": int(actor_id),
        "owner_id": int(owner_id),
        "stage": normalized_stage,
        "stop_after_stage": normalized_stage,
        "audit_reason": audit_reason.strip(),
        "limit": bounded_limit,
        "scan_limit": scan_limit,
        "scanned": len(rows),
        "matched": len(candidate_items),
        "selected": len(selected),
        "selected_pages": sum(max(int(doc.total_pages or 1), 1) for doc in selected),
        "priority": bounded_priority,
        "filters": {
            "document_ids": exact_ids,
            "extensions": normalized_extensions,
            "filename_contains": filename_filter,
        },
        "candidate_document_ids": [int(doc.id) for doc in selected],
        "candidate_items": candidate_items,
        "skipped": len(skipped_items),
        "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
        "skipped_items": skipped_items[:100],
        "requires_confirm": bool(dry_run),
        "confirm_token": CONFIRM_ENQUEUE_PIPELINE_STAGE_BATCH if dry_run else None,
    }
    if dry_run:
        return {
            **base,
            "would_enqueue": len(selected),
            "enqueued": 0,
            "already_in_flight": 0,
            "enqueued_items": [],
        }

    enqueued_items: list[dict[str, Any]] = []
    already_in_flight = 0
    for doc in selected:
        task_info = await enqueue_pipeline_stage_task(
            db,
            doc,
            int(owner_id),
            normalized_stage,
            priority=bounded_priority,
            stop_after_stage=normalized_stage,
            requested_by=f"user:{int(actor_id)}:admin-stage-batch",
            trigger="knowledge.admin.stage_batch",
            audit_reason=audit_reason,
            allow_degraded_parse=normalized_stage == "fusion",
        )
        item = {
            **_document_item(doc, reason=str(task_info.get("reason") or "stage_created")),
            "task_id": task_info.get("task_id"),
            "enqueued": bool(task_info.get("enqueued")),
        }
        enqueued_items.append(item)
        if not task_info.get("enqueued"):
            already_in_flight += 1

    await db.commit()
    return {
        **base,
        "would_enqueue": 0,
        "enqueued": len(enqueued_items) - already_in_flight,
        "already_in_flight": already_in_flight,
        "enqueued_items": enqueued_items,
        "requires_confirm": False,
        "confirm_token": None,
    }
