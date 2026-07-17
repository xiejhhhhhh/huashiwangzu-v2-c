"""Office 工作区首页 API（WP5 骨架）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.office_workspace_service import office_home

router = APIRouter(prefix="/api/office", tags=["office-workspace"])


@router.get("/home")
async def get_office_home(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await office_home(db, owner_id=user.id)
    return ApiResponse(data=data)
