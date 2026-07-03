"""Guarded reconcile for orphan knowledge pipeline diagnostic runs."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.models.file import File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbDocument, KbPipelineRun, KbPipelineStageRun

RECONCILABLE_CATEGORIES = {
    "doc_missing",
    "doc_deleted",
    "source_file_missing",
    "source_file_deleted",
}
TERMINAL_STATUS = "skipped"
RECONCILE_ACTOR = "knowledge_orphan_pipeline_run_reconcile"


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _category_for(run: KbPipelineRun, doc: KbDocument | None, file: File | None) -> str:
    _ = run
    if doc is None:
        return "doc_missing"
    if doc.deleted:
        return "doc_deleted"
    if file is None:
        return "source_file_missing"
    if file.deleted:
        return "source_file_deleted"
    return "live_without_task"


def _suggested_action(category: str) -> str:
    if category in {"source_file_missing", "source_file_deleted"}:
        return "mark_orphan_run_skipped_source_unavailable"
    if category in {"doc_missing", "doc_deleted"}:
        return "archive_orphan_diagnostic_run"
    return "manual_review_live_running_without_task"


def _latest_stage_payload(stage: KbPipelineStageRun | None) -> dict[str, Any] | None:
    if stage is None:
        return None
    return {
        "stage_run_id": stage.id,
        "stage": stage.stage,
        "status": stage.status,
        "reason": stage.reason,
        "error_message": stage.error_message,
        "started_at": _iso(stage.started_at),
        "completed_at": _iso(stage.completed_at),
    }


async def _load_latest_stages(
    db: AsyncSession,
    run_ids: list[int],
) -> dict[int, KbPipelineStageRun]:
    if not run_ids:
        return {}
    result = await db.execute(
        select(KbPipelineStageRun)
        .where(KbPipelineStageRun.run_id.in_(run_ids))
        .order_by(KbPipelineStageRun.run_id.asc(), KbPipelineStageRun.id.asc())
    )
    latest: dict[int, KbPipelineStageRun] = {}
    for stage in result.scalars().all():
        latest[int(stage.run_id or 0)] = stage
    return latest


async def _load_orphan_runs(
    db: AsyncSession,
    *,
    limit: int = 500,
    run_ids: list[int] | None = None,
) -> list[KbPipelineRun]:
    filters = [
        KbPipelineRun.status == "running",
        KbPipelineRun.task_id.is_(None),
    ]
    if run_ids:
        filters.append(KbPipelineRun.id.in_(run_ids))
    result = await db.execute(
        select(KbPipelineRun)
        .where(*filters)
        .order_by(KbPipelineRun.id.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _collect_reconcile_items(
    db: AsyncSession,
    *,
    limit: int = 500,
    run_ids: list[int] | None = None,
) -> tuple[list[KbPipelineRun], list[dict[str, Any]], Counter[str]]:
    runs = await _load_orphan_runs(db, limit=limit, run_ids=run_ids)
    latest_by_run = await _load_latest_stages(db, [int(run.id) for run in runs])
    items: list[dict[str, Any]] = []
    summary: Counter[str] = Counter()

    for run in runs:
        doc = await db.get(KbDocument, run.document_id)
        file = await db.get(File, run.file_id)
        category = _category_for(run, doc, file)
        summary[category] += 1
        would_set_status = TERMINAL_STATUS if category in RECONCILABLE_CATEGORIES else None
        would_set_reason = category if category in RECONCILABLE_CATEGORIES else None
        latest_stage = latest_by_run.get(int(run.id))
        items.append({
            "run_id": run.id,
            "document_id": run.document_id,
            "file_id": run.file_id,
            "category": category,
            "suggested_action": _suggested_action(category),
            "would_set_status": would_set_status,
            "would_set_reason": would_set_reason,
            "latest_stage": _latest_stage_payload(latest_stage),
            "run_status": run.status,
            "task_id": run.task_id,
            "started_at": _iso(run.started_at),
            "updated_at": _iso(run.updated_at),
        })

    return runs, items, summary


async def dry_run_orphan_pipeline_run_reconcile(
    db: AsyncSession,
    *,
    limit: int = 500,
    run_ids: list[int] | None = None,
) -> dict[str, Any]:
    """List running diagnostic runs that have no queue task and no live owner."""
    _, items, summary = await _collect_reconcile_items(db, limit=limit, run_ids=run_ids)
    would_change_by_category = Counter(
        item["category"]
        for item in items
        if item["category"] in RECONCILABLE_CATEGORIES
    )
    skipped_by_category = Counter(
        item["category"]
        for item in items
        if item["category"] not in RECONCILABLE_CATEGORIES
    )
    return {
        "dry_run": True,
        "matched": len(items),
        "summary": dict(summary),
        "would_change": sum(would_change_by_category.values()),
        "would_change_by_category": dict(would_change_by_category),
        "skipped_by_category": dict(skipped_by_category),
        "items": items,
        "terminal_status": TERMINAL_STATUS,
        "note": "Only running kb_pipeline_runs with task_id NULL are considered; live source rows are review-only.",
    }


def _merge_diagnostics(run: KbPipelineRun, item: dict[str, Any], now: datetime) -> dict[str, Any]:
    previous = run.diagnostics_json
    merged: dict[str, Any] = dict(previous) if isinstance(previous, dict) else {}
    merged.update({
        "previous_status": run.status,
        "previous_reason": run.reason,
        "previous_diagnostics": previous,
        "reconciled_by": RECONCILE_ACTOR,
        "reconciled_at": now.isoformat(),
        "reconcile_category": item["category"],
        "latest_stage": item.get("latest_stage"),
    })
    return merged


async def apply_orphan_pipeline_run_reconcile(
    db: AsyncSession,
    *,
    limit: int = 500,
    run_ids: list[int] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Apply guarded terminal reconcile to lifecycle-obsolete orphan runs.

    The terminal status is ``skipped`` because these diagnostic runs did not fail
    at execution time; the source document/file lifecycle made them impossible
    to continue. This matches the orchestrator's source-unavailable semantics.
    """
    runs, items, summary = await _collect_reconcile_items(db, limit=limit, run_ids=run_ids)
    runs_by_id = {int(run.id): run for run in runs}
    changed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    changed_by_category: Counter[str] = Counter()
    skipped_by_category: Counter[str] = Counter()
    now = datetime.now(timezone.utc)

    for item in items:
        category = str(item["category"])
        run = runs_by_id.get(int(item["run_id"]))
        if run is None:
            continue
        if category not in RECONCILABLE_CATEGORIES:
            skipped_item = {**item, "skip_reason": "category_not_reconcilable"}
            skipped.append(skipped_item)
            skipped_by_category[category] += 1
            continue

        changed.append(item)
        changed_by_category[category] += 1
        if dry_run:
            continue

        run.diagnostics_json = _merge_diagnostics(run, item, now)
        run.status = TERMINAL_STATUS
        run.reason = str(item["would_set_reason"] or category)
        run.completed_at = now

    if changed and not dry_run:
        await db.commit()

    return {
        "dry_run": dry_run,
        "matched": len(items),
        "changed": len(changed),
        "skipped": len(skipped),
        "summary": dict(summary),
        "changed_by_category": dict(changed_by_category),
        "skipped_by_category": dict(skipped_by_category),
        "changed_items": changed,
        "skipped_items": skipped,
        "terminal_status": TERMINAL_STATUS,
    }
