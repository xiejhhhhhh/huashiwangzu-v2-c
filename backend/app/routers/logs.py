from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.system import SystemLogResponse, SystemLogDetailResponse, FrontendErrorRequest
from app.middleware.auth import get_current_user, require_permission
from app.models.user import User
from app.models.system import SystemLog
from app.services.log_service import write_log

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/")
async def list_logs(
    level: str = Query(None), module: str = Query(None),
    keyword: str = Query(None), page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    q = select(SystemLog).order_by(desc(SystemLog.id))
    if level:
        q = q.where(SystemLog.level == level)
    if module:
        q = q.where(SystemLog.module == module)
    if keyword:
        q = q.where(SystemLog.message.ilike(f"%{keyword}%"))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    r = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    items = [SystemLogResponse.model_validate(i) for i in r.scalars().all()]
    return ApiResponse(data=PaginatedResponse(items=items, total=total or 0, page=page, page_size=page_size))


@router.post("/frontend-error")
async def report_frontend_error(
    body: FrontendErrorRequest, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await write_log(db, "warning", "frontend", "frontend_error",
                    body.error_message or "Frontend API error",
                    user_id=current_user.id,
                    data={"url": body.url, "status_code": body.status_code, "page_path": body.page_path})
    return ApiResponse(data={"ok": True})


@router.get("/{log_id}")
async def get_log_detail(
    log_id: int, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    log = await db.get(SystemLog, log_id)
    if not log:
        return ApiResponse(success=False, error="Log not found", data=None)
    return ApiResponse(data=SystemLogDetailResponse.model_validate(log))
