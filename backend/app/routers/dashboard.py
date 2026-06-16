from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.system import DashboardOverview, RecentLogItem, RecentTaskItem
from app.middleware.auth import require_permission
from app.models.user import User
from app.models.file import File
from app.models.system import SystemLog, SystemTaskQueue
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def dashboard_overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    ucount = await db.scalar(select(func.count(User.id)))
    online = await db.scalar(
        select(func.count(User.id)).where(User.last_login >= datetime.now(timezone.utc) - timedelta(days=1))
    ) if hasattr(User, 'last_login') else 0
    fcount = await db.scalar(select(func.count(File.id)).where(File.deleted == False))
    lcount = await db.scalar(select(func.count(SystemLog.id)))
    tcount = await db.scalar(
        select(func.count(SystemTaskQueue.id)).where(SystemTaskQueue.status == "pending")
    )
    return ApiResponse(data=DashboardOverview(
        total_users=ucount or 0, online_users=online or 0,
        total_files=fcount or 0, total_logs=lcount or 0,
        pending_tasks=tcount or 0,
        system_version="v2.0.0", project_name="华世王镞",
    ))


@router.get("/recent-logs")
async def recent_logs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    r = await db.execute(
        select(SystemLog).order_by(desc(SystemLog.id)).limit(10)
    )
    items = [RecentLogItem(id=i.id, level=i.level, module=i.module,
                           message=i.message[:100], created_at=i.created_at)
             for i in r.scalars().all()]
    return ApiResponse(data=items)


@router.get("/recent-tasks")
async def recent_tasks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    r = await db.execute(
        select(SystemTaskQueue).order_by(desc(SystemTaskQueue.id)).limit(10)
    )
    items = [RecentTaskItem(id=i.id, task_type=i.task_type,
                            status=i.status, created_at=i.created_at)
             for i in r.scalars().all()]
    return ApiResponse(data=items)
