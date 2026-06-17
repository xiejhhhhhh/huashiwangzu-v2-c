from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.system import *
from app.middleware.auth import require_permission
from app.models.user import User
from app.services import system_service as svc
from app.core.exceptions import NotFound
from app.services.file_share_service import check_file_access

router = APIRouter(tags=["system-old"])

# ── Dashboard (kept for backward compat, main routes now in dashboard.py) ──
@router.get("/api/dashboard/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=await svc.get_dashboard_stats(db))



# ── My Personal Tasks (moved from /api/tasks to /api/my-tasks) ──
@router.get("/api/my-tasks")
async def get_my_tasks(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    items = await svc.get_tasks(db, user.id)
    return ApiResponse(data=[TaskResponse.model_validate(i) for i in items])

# ── File Preview ──
import os
@router.get("/api/desktop/file-preview/{file_id}")
async def file_preview(file_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_permission("viewer"))):
    from app.models.file import File as FileModel
    f = await db.get(FileModel, file_id)
    if not f: raise NotFound("File not found")
    access = await check_file_access(db, file_id, user.id)
    if not access["accessible"]:
        raise NotFound("File not found")
    return ApiResponse(data={"id": f.id, "name": f"{f.name}.{f.extension}", "size": f.size, "mime_type": f.mime_type})
