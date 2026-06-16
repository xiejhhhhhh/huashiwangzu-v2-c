from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.system import BackupItem, BackupDetailResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services import backup_service as svc

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/")
async def backup_list(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    items = svc.get_backup_list()
    return ApiResponse(data=[BackupItem(**i) for i in items])


@router.get("/{backup_name}")
async def backup_detail(
    backup_name: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    detail = svc.get_backup_detail(backup_name)
    if detail is None:
        return ApiResponse(success=False, error="Backup not found", data=None)
    return ApiResponse(data=BackupDetailResponse(**detail))
