from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFound
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.app import AppResponse, AppUpdateRequest, AppCreateRequest
from app.middleware.auth import get_current_user, require_permission
from app.models.user import User
from app.models.app import App
from app.services.app_service import (
    list_apps, get_app_by_key, get_app_by_id, update_app_enabled,
    update_app, create_app, app_to_dict, sync_apps_from_manifest
)

router = APIRouter(prefix="/api/app-manager", tags=["app-manager"])


@router.get("/apps")
async def manager_list_apps(
    category: str | None = None,
    include_disabled: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    """List all apps (admin view, includes disabled if requested)."""
    from sqlalchemy import select
    query = select(App).order_by(App.sort_order)
    if category:
        query = query.where(App.category == category)
    if not include_disabled:
        query = query.where(App.enabled == True)
    result = await db.execute(query)
    apps = result.scalars().all()
    return ApiResponse(data=[app_to_dict(app) for app in apps])


@router.get("/apps/{app_id}")
async def manager_get_app(
    app_id: str = Path(..., description="App key or ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    app = await get_app_by_key(db, app_id)
    if not app:
        try:
            app = await get_app_by_id(db, int(app_id))
        except (ValueError, TypeError):
            pass
    if not app:
        raise NotFound("App not found")
    return ApiResponse(data=app_to_dict(app))


@router.put("/apps/{app_id}")
async def manager_update_app(
    data: AppUpdateRequest,
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    app = await update_app(db, app_id, update_data)
    if not app:
        raise NotFound("App not found")
    return ApiResponse(data=app_to_dict(app))


@router.put("/apps/{app_id}/toggle")
async def manager_toggle_app(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    app = await get_app_by_id(db, app_id)
    if not app:
        raise NotFound("App not found")
    app.enabled = not app.enabled
    await db.commit()
    await db.refresh(app)
    return ApiResponse(data=app_to_dict(app))


@router.post("/apps")
async def manager_create_app(
    data: AppCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    existing = await get_app_by_key(db, data.key)
    if existing:
        raise ConflictError("App key already exists")
    app = await create_app(db, data.model_dump())
    return ApiResponse(data=app_to_dict(app))


@router.post("/apps/scan-register")
async def manager_scan_register_apps(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    result = await sync_apps_from_manifest(db)
    return ApiResponse(data=result)
