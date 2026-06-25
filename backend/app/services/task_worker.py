"""Framework-level background task worker — unified trace / attempt / stale reclaim.

Consumes SystemTaskQueue (framework_system_task_queues). Concurrency-safe via
FOR UPDATE SKIP LOCKED. Modules register handlers by task_type.

Diagnostics contract (shared with hooks / gateway):
  - trace_id       : propagated from caller through handler execution
  - attempt        : retry/attempt counter embedded in result metadata
  - stale_reclaim  : per-cycle count of stale tasks reclaimed
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Awaitable, Callable

from sqlalchemy import select, update, and_, or_

from app.database import AsyncSessionLocal
from app.models.system import SystemTaskQueue

logger = logging.getLogger("v2.task_worker")

POLL_INTERVAL_SECONDS = 2.0
RUNNING_TIMEOUT_SECONDS = 1200  # running 超过 20 分钟视为死任务，回收重排

# task_type -> async handler(parameters: dict) -> dict | None
TaskHandler = Callable[[dict], Awaitable[dict | None]]
_HANDLERS: dict[str, TaskHandler] = {}

_worker_task: asyncio.Task | None = None
_stop_flag = False
_last_active: datetime | None = None

# -- Diagnostic counters (per-worker, NOT cross-worker consistent) --
_stale_reclaimed_count: int = 0
_total_tasks_processed: int = 0


def register_task_handler(task_type: str, handler: TaskHandler) -> None:
    """模块调用此函数注册自己的任务处理器。"""
    _HANDLERS[task_type] = handler
    logger.info("Registered task handler: %s", task_type)


async def _echo_handler(parameters: dict) -> dict:
    """内置自检处理器，用于验证 worker 链路。"""
    return {"echo": parameters}


_HANDLERS["_echo"] = _echo_handler


async def _reconcile_one_orphan(task: SystemTaskQueue, now: datetime) -> None:
    """Increment retry_count on an orphan task and fail it if over limit."""
    task.retry_count = (task.retry_count or 0) + 1
    if task.retry_count >= (task.max_retries or 3):
        task.status = "failed"
        task.error_message = "Orphan task exceeded max retries on startup recovery"
        task.completed_at = now
    else:
        task.status = "pending"
        task.started_at = None


async def _recover_stale_tasks(db) -> None:
    global _stale_reclaimed_count
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=RUNNING_TIMEOUT_SECONDS)

    # Phase 1: timeout-reclaim — running tasks older than cutoff
    result = await db.execute(
        select(SystemTaskQueue)
        .where(SystemTaskQueue.status == "running", SystemTaskQueue.started_at < cutoff)
        .with_for_update(skip_locked=True)
    )
    stale = list(result.scalars().all())
    for task in stale:
        task.retry_count = (task.retry_count or 0) + 1
        if task.retry_count >= (task.max_retries or 3):
            task.status = "failed"
            task.error_message = "Task timed out and exceeded max retries"
            task.completed_at = now
        else:
            task.status = "pending"
            task.started_at = None
    if stale:
        _stale_reclaimed_count += len(stale)
        logger.info("Timeout recovery: reclaimed %d stale tasks (cumulative: %d)", len(stale), _stale_reclaimed_count)
    await db.commit()


async def _recover_orphan_running_tasks() -> None:
    """Startup recovery: reset all running tasks to pending+retry.

    Called once when the worker starts.  Any task still marked 'running'
    at this point is guaranteed to be an orphan from a dead process.
    """
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(
                select(SystemTaskQueue)
                .where(SystemTaskQueue.status == "running")
                .with_for_update(skip_locked=True)
            )
            orphans = list(result.scalars().all())
            for task in orphans:
                await _reconcile_one_orphan(task, now)
            await db.commit()
            failed_count = sum(
                1 for t in orphans
                if t.retry_count >= (t.max_retries or 3) and t.status == "failed"
            )
            logger.info(
                "Orphan recovery: reset %d running tasks (retry_count incremented, "
                "%d marked failed)",
                len(orphans), failed_count,
            )
    except Exception as exc:
        logger.error("Orphan recovery failed: %s", exc)


async def _claim_one_task(db) -> SystemTaskQueue | None:
    """原子抢占一条 pending 任务（FOR UPDATE SKIP LOCKED 防多 worker 抢同一条）。
    
    即时任务(scheduled_at IS NULL)照旧立即执行；
    定时任务(scheduled_at <= now())到点才被取。
    """
    now = datetime.now(timezone.utc)
    row = await db.execute(
        select(SystemTaskQueue)
        .where(
            and_(
                SystemTaskQueue.status == "pending",
                or_(
                    SystemTaskQueue.scheduled_at.is_(None),
                    SystemTaskQueue.scheduled_at <= now,
                ),
            )
        )
        .order_by(SystemTaskQueue.priority.desc(), SystemTaskQueue.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = row.scalar_one_or_none()
    if not task:
        return None
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    return task


async def _run_handler(task: SystemTaskQueue) -> tuple[bool, dict | None, str | None]:
    handler = _HANDLERS.get(task.task_type)
    if not handler:
        return False, None, f"No handler registered for task_type '{task.task_type}'"
    try:
        params = json.loads(task.parameters) if task.parameters else {}
    except Exception as exc:
        return False, None, f"Invalid parameters JSON: {exc}"

    # Inject trace_id and attempt into params for downstream diagnostics
    trace_id = params.pop("_trace_id", str(uuid.uuid4()))
    attempt = (task.retry_count or 0) + 1
    params["_trace_id"] = trace_id
    params["_attempt"] = attempt

    try:
        result = await handler(params)
        return True, result, None
    except Exception as exc:
        logger.error("Task %s (%s) handler failed (trace=%s attempt=%d): %s", task.id, task.task_type, trace_id, attempt, exc)
        return False, None, str(exc)


def _compute_next_recur(recur: str, ref_time: datetime) -> datetime | None:
    """根据周期表达计算下一次运行时间。"""
    ref = ref_time.astimezone(timezone.utc)
    if recur == "hourly":
        return ref + timedelta(hours=1)
    elif recur == "daily":
        return ref + timedelta(days=1)
    elif recur == "weekly":
        return ref + timedelta(weeks=1)
    elif recur.startswith("cron:"):
        # Minimal cron: "cron:HH:MM" daily at that UTC time
        parts = recur.split(":")
        if len(parts) >= 3:
            hour, minute = int(parts[1]), int(parts[2])
            next_time = ref.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_time <= ref:
                next_time += timedelta(days=1)
            return next_time
    return None


async def _finish_task(db, task_id: int, ok: bool, result: dict | None, error: str | None) -> None:
    global _total_tasks_processed
    task = await db.get(SystemTaskQueue, task_id)
    if not task:
        return
    _total_tasks_processed += 1
    now = datetime.now(timezone.utc)
    if ok:
        task.status = "completed"
        task.result = json.dumps(result, ensure_ascii=False) if result is not None else None
        task.error_message = None
        task.completed_at = now
        # 周期任务: 完成后自动重排下一次
        if task.recur:
            next_time = _compute_next_recur(task.recur, now)
            if next_time:
                task.status = "pending"
                task.scheduled_at = next_time
                task.next_run_at = next_time
                task.started_at = None
                task.retry_count = 0
                task.completed_at = None
    else:
        task.retry_count = (task.retry_count or 0) + 1
        task.error_message = error
        if task.retry_count >= (task.max_retries or 3):
            task.status = "failed"
            task.completed_at = now
        else:
            task.status = "pending"  # 重排重试
            task.started_at = None
    await db.commit()


async def _worker_loop() -> None:
    global _last_active
    logger.info("Task worker loop started")
    # Startup: reclaim any orphan running tasks from a dead process
    await _recover_orphan_running_tasks()
    while not _stop_flag:
        try:
            async with AsyncSessionLocal() as db:
                await _recover_stale_tasks(db)
                task = await _claim_one_task(db)
            if task is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue
            _last_active = datetime.now(timezone.utc)
            ok, result, error = await _run_handler(task)
            async with AsyncSessionLocal() as db:
                await _finish_task(db, task.id, ok, result, error)
        except Exception as exc:
            logger.error("Task worker loop error: %s", exc)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    logger.info("Task worker loop stopped")


def start_worker() -> None:
    global _worker_task, _stop_flag
    _stop_flag = False
    _worker_task = asyncio.create_task(_worker_loop())


async def stop_worker() -> None:
    global _stop_flag
    _stop_flag = True
    if _worker_task:
        try:
            await asyncio.wait_for(_worker_task, timeout=POLL_INTERVAL_SECONDS + 1)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _worker_task.cancel()


def worker_health() -> dict:
    return {
        "running": _worker_task is not None and not _worker_task.done(),
        "registered_handlers": sorted(_HANDLERS.keys()),
        "last_active": _last_active.isoformat() if _last_active else None,
        "diagnostics": {
            "stale_reclaimed_count": _stale_reclaimed_count,
            "total_tasks_processed": _total_tasks_processed,
            "handler_count": len(_HANDLERS),
        },
    }
