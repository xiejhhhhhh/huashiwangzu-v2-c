from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.private_module_service import (
    preview_private_module,
    install_private_module,
    activate_private_module,
    deactivate_private_module,
    uninstall_private_module,
    rollback_private_module,
    list_private_modules,
    list_workspace_private_modules,
)

router = APIRouter(prefix="/api/private-modules", tags=["private-modules"])


class PrivateModuleActionRequest(BaseModel):
    module_key: str
    module_type: str = "module"
    force: bool = False


class PrivateModulePreviewRequest(BaseModel):
    module_key: str
    module_type: str = "module"


@router.post("/preview")
async def api_preview_private_module(
    payload: PrivateModulePreviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    result = await preview_private_module(
        db, user.id, payload.module_key, payload.module_type
    )
    return ApiResponse(data=result)


@router.post("/install")
async def api_install_private_module(
    payload: PrivateModuleActionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    result = await install_private_module(
        db, user.id, payload.module_key, payload.module_type
    )
    return ApiResponse(data=result)


@router.post("/{module_key}/activate")
async def api_activate_private_module(
    module_key: str = Path(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    result = await activate_private_module(db, user.id, module_key)
    return ApiResponse(data=result)


@router.post("/{module_key}/deactivate")
async def api_deactivate_private_module(
    module_key: str = Path(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    result = await deactivate_private_module(db, user.id, module_key)
    return ApiResponse(data=result)


@router.delete("/{module_key}")
async def api_uninstall_private_module(
    module_key: str = Path(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    result = await uninstall_private_module(db, user.id, module_key)
    return ApiResponse(data=result)


@router.post("/{module_key}/rollback")
async def api_rollback_private_module(
    module_key: str = Path(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    result = await rollback_private_module(db, user.id, module_key)
    return ApiResponse(data=result)


@router.get("")
async def api_list_private_modules(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    installed = await list_private_modules(db, user.id)
    available = await list_workspace_private_modules(user.id)
    return ApiResponse(data={
        "installed": installed,
        "available_in_workspace": available,
    })
