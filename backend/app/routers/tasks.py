from fastapi import APIRouter, Depends
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.system import SystemTaskQueueResponse, WorkerStatusResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.models.system import SystemTaskQueue
from datetime import datetime, timezone

router = APIRouter(prefix="/api/tasks", tags=["system-tasks"])


@router.get("/")
async def task_list(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    r = await db.execute(
        select(SystemTaskQueue).order_by(desc(SystemTaskQueue.id)).limit(50)
    )
    items = [SystemTaskQueueResponse.model_validate(i) for i in r.scalars().all()]
    return ApiResponse(data=items)


@router.get("/worker/status")
async def worker_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    r = await db.execute(
        select(SystemTaskQueue.status, func.count(SystemTaskQueue.id))
        .group_by(SystemTaskQueue.status)
    )
    counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
    for row in r.all():
        counts[row[0]] = row[1]
    oldest = await db.scalar(
        select(SystemTaskQueue.created_at)
        .where(SystemTaskQueue.status == "pending")
        .order_by(SystemTaskQueue.created_at).limit(1)
    )
    wait_secs = int((datetime.now(timezone.utc) - oldest).total_seconds()) if oldest else None
    return ApiResponse(data=WorkerStatusResponse(
        pending=counts["pending"], running=counts["running"],
        completed=counts["completed"], failed=counts["failed"],
        oldest_waiting_seconds=wait_secs,
    ))


@router.get("/{task_id}")
async def task_detail(
    task_id: int, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    task = await db.get(SystemTaskQueue, task_id)
    if not task:
        return ApiResponse(success=False, error="Task not found", data=None)
    return ApiResponse(data=SystemTaskQueueResponse.model_validate(task))


@router.post("/{task_id}/retry")
async def retry_task(
    task_id: int, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    task = await db.get(SystemTaskQueue, task_id)
    if not task:
        return ApiResponse(success=False, error="Task not found", data=None)
    task.status = "pending"
    task.retry_count = 0
    task.error_message = None
    await db.commit()
    return ApiResponse(data={"ok": True, "message": "Task re-queued"})


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: int, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    task = await db.get(SystemTaskQueue, task_id)
    if not task:
        return ApiResponse(success=False, error="Task not found", data=None)
    task.status = "failed"
    task.error_message = "Manually cancelled"
    task.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return ApiResponse(data={"ok": True, "message": "Task cancelled"})
