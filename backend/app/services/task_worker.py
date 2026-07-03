"""Framework-level background task worker.

Consumes SystemTaskQueue (framework_system_task_queues). Concurrency-safe via
FOR UPDATE SKIP LOCKED. Modules register handlers by task_type.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy import and_, or_, select, update

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
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=RUNNING_TIMEOUT_SECONDS)

    # Phase 1: timeout-reclaim — running tasks older than cutoff
    result = await db.execute(
        select(SystemTaskQueue)
        .where(SystemTaskQueue.status == "running", SystemTaskQueue.started_at < cutoff)
        .with_for_update(skip_locked=True)
    )
    stale = list(result.scalars().all())
    reclaimed_count = 0
    for task in stale:
        retry_count = (task.retry_count or 0) + 1
        if retry_count >= (task.max_retries or 3):
            values = {
                "retry_count": retry_count,
                "status": "failed",
                "error_message": "Task timed out and exceeded max retries",
                "completed_at": now,
            }
        else:
            values = {
                "retry_count": retry_count,
                "status": "pending",
                "started_at": None,
            }
        update_result = await db.execute(
            update(SystemTaskQueue)
            .where(
                SystemTaskQueue.id == task.id,
                SystemTaskQueue.status == "running",
                SystemTaskQueue.started_at == task.started_at,
            )
            .values(**values)
        )
        reclaimed_count += int(update_result.rowcount or 0)
    if reclaimed_count:
        logger.info("Timeout recovery: reclaimed %d stale tasks", reclaimed_count)
    await db.commit()


async def _recover_orphan_running_tasks() -> None:
    """Startup recovery: reclaim only timed-out running tasks.

    In multi-worker deployments another worker may legitimately be executing a
    fresh ``running`` task while this worker starts. Treating every running task
    as orphaned causes duplicate retries, so startup recovery uses the same
    timeout + row-lock path as periodic stale recovery.
    """
    try:
        async with AsyncSessionLocal() as db:
            await _recover_stale_tasks(db)
    except Exception as exc:
        logger.error("Orphan recovery failed: %s", exc)


def _result_is_semantic_failure(result: dict | None) -> tuple[bool, str | None]:
    """Return whether a handler result is a business failure contract."""
    if not isinstance(result, dict):
        return False, None
    if result.get("success") is False:
        return True, str(result.get("error") or "Task result success=false")
    status = result.get("status")
    if isinstance(status, str) and status.lower() in {"failed", "error"}:
        return True, str(result.get("error") or f"Task result status={status}")
    if result.get("error") not in (None, "") and result.get("success") is not True:
        return True, str(result.get("error"))
    return False, None


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
    try:
        result = await handler(params)
        failed, error = _result_is_semantic_failure(result)
        if failed:
            return False, result, error
        return True, result, None
    except Exception as exc:
        logger.error("Task %s (%s) handler failed: %s", task.id, task.task_type, exc)
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
    task = await db.get(SystemTaskQueue, task_id)
    if not task:
        return
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
        "process_local": True,
        "pid": os.getpid(),
        "last_active_scope": "process",
    }
