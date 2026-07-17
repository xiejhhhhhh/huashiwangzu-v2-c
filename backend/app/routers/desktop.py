from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.desktop_state import DesktopAuditLogRequest, DesktopStateSaveRequest
from app.services import app_service
from app.services.desktop_state_service import get_state, save_state
from app.services.log_service import write_log

router = APIRouter(prefix="/api/desktop", tags=["desktop"])


@router.get("/apps")
async def list_apps(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    result = await app_service.list_apps(db, current_user, category)
    return ApiResponse(data=[app_service.app_to_dict(app) for app in result])


@router.get("/apps/{app_key}")
async def get_app_detail(
    app_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    app = await app_service.get_app_by_key(db, app_key)
    if not app or not app.enabled or not app_service.can_user_access_app(app, current_user):
        raise NotFound("App not found")
    return ApiResponse(data=app_service.app_to_dict(app))


@router.get("/state")
async def get_desktop_state(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    state = await get_state(db, current_user.id)
    if not state:
        return ApiResponse(data={"user_id": current_user.id, "state_json": {}, "version": 1})
    return ApiResponse(data={
        "user_id": state.user_id,
        "state_json": state.state_json,
        "version": state.version,
    })


async def _save_desktop_state(
    data: DesktopStateSaveRequest,
    db: AsyncSession,
    current_user: User,
):
    state = await save_state(
        db,
        current_user.id,
        data.state_json,
        expected_version=data.expected_version,
    )
    return ApiResponse(data={
        "user_id": state.user_id,
        "state_json": state.state_json,
        "version": state.version,
    })


@router.put("/state")
async def put_desktop_state(
    data: DesktopStateSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    return await _save_desktop_state(data, db, current_user)


@router.post("/state")
async def post_desktop_state(
    data: DesktopStateSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    return await _save_desktop_state(data, db, current_user)


@router.post("/audit-log")
async def write_desktop_audit_log(
    data: DesktopAuditLogRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await write_log(
        db, "info", "desktop", "audit_log",
        data.action or "desktop action",
        user_id=current_user.id,
        data={"params": data.params, "target_app": data.target_app},
    )
    return ApiResponse(data={"ok": True})
