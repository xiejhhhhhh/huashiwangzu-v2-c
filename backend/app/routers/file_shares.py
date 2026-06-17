from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services import file_share_service as svc
from app.schemas.common import ApiResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/files/share", tags=["File Shares"])


class ShareCreateRequest(BaseModel):
    file_id: int
    target_user_id: int
    permission: str = "read"


@router.post("")
async def create_share(
    body: ShareCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    share = await svc.create_share(
        db,
        file_id=body.file_id,
        shared_by_user_id=current_user.id,
        shared_with_user_id=body.target_user_id,
        permission=body.permission,
    )
    return ApiResponse(success=True, data={
        "id": share.id,
        "file_id": share.file_id,
        "shared_by_owner_id": share.shared_by_owner_id,
        "shared_with_user_id": share.shared_with_user_id,
        "permission": share.permission,
        "created_at": share.created_at.isoformat() if share.created_at else None,
    })


@router.get("/received")
async def received_shares(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    keyword: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await svc.get_received_shares(db, current_user.id, page, page_size, keyword)
    return ApiResponse(success=True, data=result)


@router.get("/sent")
async def sent_shares(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await svc.get_sent_shares(db, current_user.id, page, page_size)
    return ApiResponse(success=True, data=result)


@router.delete("/{share_id}")
async def delete_share(
    share_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await svc.delete_share(db, share_id, current_user.id)
    return ApiResponse(success=True, data={"message": "Share cancelled"})


@router.get("/check/{file_id}")
async def check_access(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await svc.check_file_access(db, file_id, current_user.id)
    return ApiResponse(success=True, data=result)
