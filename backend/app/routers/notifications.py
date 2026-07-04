from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.system import NotificationAdminResponse, NotificationCreate
from app.services import notification_service as svc

router = APIRouter(tags=["notifications"])


class ModuleNotificationRequest(BaseModel):
    title: str
    content: str | None = None
    notification_type: str = "info"


@router.get("/api/notifications")
async def list_notifications(
    page: int = Query(1), page_size: int = Query(20),
    db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer")),
):
    items, total = await svc.get_published_notifications(db, user.id, page, page_size)
    return ApiResponse(data={"list": items, "total": total, "page": page, "page_size": page_size})


@router.get("/api/notifications/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    count = await svc.get_unread_count(db, user.id)
    return ApiResponse(data={"unread_count": count})


@router.post("/api/notifications/{nid}/read")
async def mark_read(nid: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    await svc.mark_as_read(db, nid, user.id)
    return ApiResponse(data={"ok": True})


@router.post("/api/notifications/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    await svc.mark_all_as_read(db, user.id)
    return ApiResponse(data={"ok": True})


@router.post("/api/notifications/module")
async def module_notification(
    body: ModuleNotificationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    n = await svc.create_announcement(db, body.title, body.content or "", body.notification_type, user.id)
    return ApiResponse(data={"ok": True, "id": n.id})


@router.get("/api/notifications/admin/announcements")
async def list_announcements(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("admin")),
):
    items = await svc.get_all_announcements(db, status)
    return ApiResponse(data=[NotificationAdminResponse.model_validate(i) for i in items])


@router.post("/api/notifications/admin/announcements")
async def create_announcement(
    body: NotificationCreate,
    db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("admin")),
):
    n = await svc.create_announcement(db, body.title, body.content, body.notification_type, user.id)
    return ApiResponse(data=NotificationAdminResponse.model_validate(n))


@router.put("/api/notifications/admin/announcements/{nid}/revoke")
async def revoke_announcement(
    nid: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("admin")),
):
    n = await svc.revoke_announcement(db, nid)
    return ApiResponse(data=NotificationAdminResponse.model_validate(n))
