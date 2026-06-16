from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.recycle import RecycleItemResponse, RestoreRequest
from app.middleware.auth import get_current_user, require_permission
from app.models.user import User
from app.services import recycle_service

router = APIRouter(prefix="/api/recycle", tags=["recycle"])


@router.get("/list")
async def list_recycle(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    items = await recycle_service.get_recycle_list(db, user.id)
    return ApiResponse(data=[RecycleItemResponse.model_validate(i) for i in items])


@router.post("/restore")
async def restore(
    body: RestoreRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    await recycle_service.restore_item(db, body.item_type, body.id, user.id)
    return ApiResponse(data={"message": "Restored"})


@router.post("/delete-permanently")
async def delete_permanently(
    body: RestoreRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    await recycle_service.delete_permanently(db, body.item_type, body.id, user.id)
    return ApiResponse(data={"message": "Deleted"})


@router.post("/empty")
async def empty_trash(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    await recycle_service.empty_trash(db, user.id)
    return ApiResponse(data={"message": "Trash emptied"})
