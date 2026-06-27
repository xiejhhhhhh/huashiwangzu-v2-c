from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFound
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.system import SettingResponse, SettingCreate, SettingUpdate
from app.middleware.auth import require_permission
from app.models.user import User
from app.services import settings_service as svc

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/")
async def list_settings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    items = await svc.get_all_settings(db)
    return ApiResponse(data=[SettingResponse.model_validate(i) for i in items])


@router.get("/system-config")
async def get_system_config(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("admin"))):
    config = await svc.get_system_config_map(db)
    return ApiResponse(data=config)


@router.put("/system-config")
async def update_system_config(
    body: dict[str, str], db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    config = await svc.update_system_config(db, body)
    return ApiResponse(data=config)


@router.post("/")
async def create_setting(
    body: SettingCreate, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    s = await svc.create_setting(db, body.key, body.value, body.description)
    return ApiResponse(data=SettingResponse.model_validate(s))


@router.get("/{key}")
async def get_setting(
    key: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    s = await svc.get_setting(db, key)
    if not s:
        raise NotFound("Setting not found")
    return ApiResponse(data=SettingResponse.model_validate(s))


@router.put("/{key}")
async def update_setting(
    key: str, body: SettingUpdate, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    s = await svc.update_setting(db, key, body.value, body.description)
    return ApiResponse(data=SettingResponse.model_validate(s))


@router.delete("/{key}")
async def delete_setting(
    key: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    await svc.delete_setting(db, key)
    return ApiResponse(data={"ok": True})
