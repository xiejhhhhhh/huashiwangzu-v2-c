"""Task queue audit service — classify historical debt, detect new failures, reconcile orphans.

This service is the authoritative source for understanding the task queue's debts:
failed/pending tasks accumulated over time, recent failures that need review, and
orphan work that may be safely reconciled. It never clears failed rows to fake health.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import SystemTaskQueue
from app.services.module_registry import semantic_failure_reason
from app.services.task_debt_governance_service import (
    KB_DELETED_SOURCE_OBSOLETE_CATEGORY,
    classify_failed_task_debt,
)

logger = logging.getLogger("v2.task_queue_audit")

STALE_PENDING_THRESHOLD_SECONDS = 3600
ORPHAN_RUNNING_TIMEOUT_SECONDS = 1200
RECENT_FAILURE_WINDOW_HOURS = 1
HISTORICAL_DEBT_CUTOFF_HOURS = RECENT_FAILURE_WINDOW_HOURS
COMPLETED_SEMANTIC_FAILURE_SAMPLE_LIMIT = 20


def _decode_task_result(raw_result: Any) -> dict[str, Any] | None:
    if isinstance(raw_result, dict):
        return raw_result
    if not isinstance(raw_result, str) or not raw_result.strip():
        return None
    try:
        decoded = json.loads(raw_result)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _task_result_semantic_failure_reason(result: dict[str, Any] | None) -> str | None:
    return semantic_failure_reason(result)


def _semantic_failure_sample(task: SystemTaskQueue, reason: str) -> dict:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "module": task.module,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "reason": reason,
        "classification": "completed_semantic_failure_manual_review",
    }


def _failed_task_sample(task: SystemTaskQueue, classification: dict | None = None) -> dict:
    sample = {
        "id": task.id,
        "task_type": task.task_type,
        "module": task.module,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "error_message": task.error_message,
    }
    if classification:
        sample["classification"] = classification.get("category")
        sample["action"] = classification.get("action")
        state_sample = classification.get("sample")
        if isinstance(state_sample, dict):
            for key in ("document_id", "doc_state", "file_state", "file_id", "physical_exists"):
                if key in state_sample:
                    sample[key] = state_sample[key]
    return sample


async def _split_recent_failed_tasks(
    db: AsyncSession,
    recent_failed_list: list[SystemTaskQueue],
) -> tuple[list[SystemTaskQueue], list[dict]]:
    active_recent: list[SystemTaskQueue] = []
    obsolete_recent: list[dict] = []
    for task in recent_failed_list:
        classification: dict | None = None
        if task.task_type in {"kb_pipeline_stage", "kb_pipeline"}:
            classification = await classify_failed_task_debt(db, task)
        if (
            classification
            and classification.get("category") == KB_DELETED_SOURCE_OBSOLETE_CATEGORY
            and classification.get("action") == "mark_obsolete"
        ):
            obsolete_recent.append(_failed_task_sample(task, classification))
            continue
        active_recent.append(task)
    return active_recent, obsolete_recent


async def audit_task_queue(db: AsyncSession) -> dict:
    """Aggregate task queue into classified buckets.

    Returns a dict with:
      - summary (pending/running/completed/failed counts)
      - debt (tasks classified as historical debt, not new failures)
      - blockers (tasks that may need immediate attention)
      - detail (per-handler, per-status breakdown)
      - stalest_pending info
    """
    counts_raw = await db.execute(
        select(SystemTaskQueue.status, func.count(SystemTaskQueue.id))
        .group_by(SystemTaskQueue.status)
    )
    counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
    for row in counts_raw.all():
        counts[row[0]] = row[1]

    now = datetime.now(timezone.utc)
    debt_cutoff = now - timedelta(hours=HISTORICAL_DEBT_CUTOFF_HOURS)

    # --- Classify failed tasks ---
    recent_failed = await db.execute(
        select(SystemTaskQueue)
        .where(
            and_(
                SystemTaskQueue.status == "failed",
                SystemTaskQueue.completed_at >= debt_cutoff,
            )
        )
        .order_by(SystemTaskQueue.completed_at.desc())
        .limit(200)
    )
    recent_failed_list = list(recent_failed.scalars().all())
    active_recent_failed_list, obsolete_recent_failed_samples = await _split_recent_failed_tasks(
        db,
        recent_failed_list,
    )

    historical_failed_filter = and_(
        SystemTaskQueue.status == "failed",
        or_(
            SystemTaskQueue.completed_at.is_(None),
            SystemTaskQueue.completed_at < debt_cutoff,
        ),
    )
    old_failed_count = await db.scalar(
        select(func.count(SystemTaskQueue.id)).where(historical_failed_filter)
    )
    historical_failed_debt_count = int(old_failed_count or 0)

    completed_with_results = await db.execute(
        select(SystemTaskQueue)
        .where(
            and_(
                SystemTaskQueue.status == "completed",
                SystemTaskQueue.result.is_not(None),
                SystemTaskQueue.result != "",
            )
        )
        .order_by(SystemTaskQueue.completed_at.desc().nulls_last(), SystemTaskQueue.id.desc())
    )
    completed_semantic_failure_count = 0
    completed_semantic_failure_samples = []
    for task in completed_with_results.scalars().all():
        reason = _task_result_semantic_failure_reason(_decode_task_result(task.result))
        if reason is None:
            continue
        completed_semantic_failure_count += 1
        if len(completed_semantic_failure_samples) < COMPLETED_SEMANTIC_FAILURE_SAMPLE_LIMIT:
            completed_semantic_failure_samples.append(_semantic_failure_sample(task, reason))

    # --- Classify pending tasks ---
    pending_tasks = await db.execute(
        select(SystemTaskQueue)
        .where(SystemTaskQueue.status == "pending")
        .order_by(SystemTaskQueue.created_at)
        .limit(200)
    )
    pending_tasks_list = list(pending_tasks.scalars().all())

    stalest_pending_info = None
    actionable_pending = []
    stale_pending = []
    unreachable_pending = []
    for t in pending_tasks_list:
        age_seconds = int((now - (t.created_at or now)).total_seconds())
        info = {
            "id": t.id,
            "task_type": t.task_type,
            "module": t.module,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "age_seconds": age_seconds,
            "retry_count": t.retry_count,
            "max_retries": t.max_retries,
            "error_message": t.error_message,
            "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
        }
        if t.scheduled_at and t.scheduled_at > now:
            info["classification"] = "future_scheduled"
            unreachable_pending.append(info)
        elif age_seconds < STALE_PENDING_THRESHOLD_SECONDS:
            info["classification"] = "recent_expected"
            actionable_pending.append(info)
        else:
            info["classification"] = "stale_pending_debt"
            stale_pending.append(info)

    if pending_tasks_list:
        stalest = pending_tasks_list[0]
        stalest_pending_info = {
            "id": stalest.id,
            "task_type": stalest.task_type,
            "module": stalest.module,
            "age_seconds": int((now - (stalest.created_at or now)).total_seconds()),
            "error_message": stalest.error_message,
            "scheduled_at": stalest.scheduled_at.isoformat() if stalest.scheduled_at else None,
        }

    # --- Classify running tasks ---
    running_tasks = await db.execute(
        select(SystemTaskQueue)
        .where(SystemTaskQueue.status == "running")
        .order_by(SystemTaskQueue.started_at.desc().nulls_last())
        .limit(100)
    )
    running_tasks_list = list(running_tasks.scalars().all())

    healthy_running = []
    orphan_running = []
    for t in running_tasks_list:
        started = t.started_at or t.created_at or now
        running_seconds = int((now - started).total_seconds())
        entry = {
            "id": t.id,
            "task_type": t.task_type,
            "module": t.module,
            "running_seconds": running_seconds,
            "started_at": t.started_at.isoformat() if t.started_at else None,
        }
        if running_seconds > ORPHAN_RUNNING_TIMEOUT_SECONDS:
            entry["classification"] = "orphan_running_debt"
            orphan_running.append(entry)
        else:
            entry["classification"] = "in_progress"
            healthy_running.append(entry)

    # --- Per-handler breakdown ---
    handler_groups = await db.execute(
        select(
            SystemTaskQueue.task_type,
            SystemTaskQueue.status,
            func.count(SystemTaskQueue.id),
        )
        .group_by(SystemTaskQueue.task_type, SystemTaskQueue.status)
    )
    handler_breakdown: dict[str, dict[str, int]] = {}
    for row in handler_groups.all():
        h = row[0] or "unknown"
        s = row[1] or "unknown"
        c = row[2]
        handler_breakdown.setdefault(h, {})[s] = c

    # --- Error signature grouping for failed ---
    error_sigs = await db.execute(
        select(
            SystemTaskQueue.task_type,
            SystemTaskQueue.error_message,
            func.count(SystemTaskQueue.id),
        )
        .where(SystemTaskQueue.status == "failed")
        .group_by(SystemTaskQueue.task_type, SystemTaskQueue.error_message)
        .order_by(func.count(SystemTaskQueue.id).desc())
        .limit(50)
    )
    top_error_signatures = [
        {
            "task_type": row[0],
            "error_snippet": (row[1] or "")[:200],
            "count": row[2],
        }
        for row in error_sigs.all()
    ]

    return {
        "summary": {
            "pending": counts["pending"],
            "running": counts["running"],
            "completed": counts["completed"],
            "failed": counts["failed"],
        },
        "classification": {
            "recent_failed_count": len(active_recent_failed_list),
            "recent_failed_total_count": len(recent_failed_list),
            "deleted_source_obsolete_failed_count": len(obsolete_recent_failed_samples),
            "historical_failed_debt_count": historical_failed_debt_count,
            "actionable_pending_count": len(actionable_pending),
            "stale_pending_debt_count": len(stale_pending),
            "future_scheduled_count": len(unreachable_pending),
            "healthy_running_count": len(healthy_running),
            "orphan_running_debt_count": len(orphan_running),
            "completed_semantic_failure_count": completed_semantic_failure_count,
            "completed_semantic_failure_manual_review_count": completed_semantic_failure_count,
        },
        "recent_failed_count": len(active_recent_failed_list),
        "recent_failed_total_count": len(recent_failed_list),
        "deleted_source_obsolete_failures": {
            "count": len(obsolete_recent_failed_samples),
            "action": "mark_obsolete",
            "category": KB_DELETED_SOURCE_OBSOLETE_CATEGORY,
            "mutates_rows": False,
            "reason": (
                "Recent failed knowledge pipeline rows whose knowledge document/source is already deleted are "
                "tracked as obsolete debt, not active parser/worker failures."
            ),
            "samples": obsolete_recent_failed_samples[:20],
        },
        "historical_debt_total": historical_failed_debt_count,
        "completed_semantic_failures": {
            "count": completed_semantic_failure_count,
            "action": "manual_review",
            "mutates_rows": False,
            "reason": (
                "Completed task rows whose result JSON still reports error/status=failed/"
                "success=false need manual review; audit does not retry, archive, or delete them."
            ),
            "samples": completed_semantic_failure_samples,
        },
        "stalest_pending": stalest_pending_info,
        "handler_breakdown": handler_breakdown,
        "top_error_signatures": top_error_signatures,
        "metadata": {
            "recent_failure_window_hours": RECENT_FAILURE_WINDOW_HOURS,
            "debt_cutoff_hours": HISTORICAL_DEBT_CUTOFF_HOURS,
            "stale_pending_threshold_seconds": STALE_PENDING_THRESHOLD_SECONDS,
            "orphan_timeout_seconds": ORPHAN_RUNNING_TIMEOUT_SECONDS,
        },
    }


async def reconcile_orphan_running(db: AsyncSession) -> list[dict]:
    """Reconcile orphan running tasks that have exceeded the timeout.

    Only touches tasks running longer than ORPHAN_RUNNING_TIMEOUT_SECONDS
    with no handler activity. Returns the list of reconciled task ids and reasons.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=ORPHAN_RUNNING_TIMEOUT_SECONDS)

    result = await db.execute(
        select(SystemTaskQueue)
        .where(
            and_(
                SystemTaskQueue.status == "running",
                SystemTaskQueue.started_at < cutoff,
            )
        )
        .with_for_update(skip_locked=True)
        .limit(50)
    )
    orphans = list(result.scalars().all())
    reconciled = []
    for task in orphans:
        age = int((now - (task.started_at or task.created_at or now)).total_seconds())
        task.retry_count = (task.retry_count or 0) + 1
        if task.retry_count >= (task.max_retries or 3):
            task.status = "failed"
            task.error_message = f"Orphan reconciled: running for {age}s exceeded timeout"
            task.completed_at = now
        else:
            task.status = "pending"
            task.started_at = None
            task.error_message = f"Orphan reconciled: re-queued after {age}s"
        reconciled.append({
            "id": task.id,
            "task_type": task.task_type,
            "reason": f"Running for {age}s, reconciled to '{task.status}'",
        })
    if orphans:
        await db.commit()
        logger.info("Reconciled %d orphan running tasks", len(orphans))
    return reconciled


async def reconcile_stale_pending(db: AsyncSession) -> list[dict]:
    """Reconcile stale pending tasks that may be stuck.

    Only touches tasks pending longer than STALE_PENDING_THRESHOLD_SECONDS
    that are NOT scheduled for the future. These are tasks that never got
    picked up — we mark them as failed with a clear reason.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=STALE_PENDING_THRESHOLD_SECONDS)

    result = await db.execute(
        select(SystemTaskQueue)
        .where(
            and_(
                SystemTaskQueue.status == "pending",
                SystemTaskQueue.created_at < cutoff,
                or_(
                    SystemTaskQueue.scheduled_at.is_(None),
                    SystemTaskQueue.scheduled_at <= now,
                ),
            )
        )
        .with_for_update(skip_locked=True)
        .limit(50)
    )
    stale = list(result.scalars().all())
    reconciled = []
    for task in stale:
        age = int((now - (task.created_at or now)).total_seconds())
        task.status = "failed"
        task.error_message = f"Stale pending reconciled: waited {age}s without processing"
        task.completed_at = now
        reconciled.append({
            "id": task.id,
            "task_type": task.task_type,
            "reason": f"Pending for {age}s without processing, marked as failed debt",
        })
    if stale:
        await db.commit()
        logger.info("Reconciled %d stale pending tasks", len(stale))
    return reconciled
