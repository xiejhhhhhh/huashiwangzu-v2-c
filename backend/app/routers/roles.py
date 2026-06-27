import logging
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.role import RoleMatrixResponse, RoleMatrixItem, RoleMatrixUpdate
from app.middleware.auth import get_current_user, require_permission
from app.models.user import User
from app.services.role_service import get_role_matrix, update_role_matrix

logger = logging.getLogger("v2.roles")

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("/matrix")
async def get_matrix(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    matrix = await get_role_matrix(db)
    return ApiResponse(data=RoleMatrixResponse(
        matrix=[RoleMatrixItem(**item) for item in matrix]
    ))


@router.put("/matrix")
async def put_matrix(
    body: RoleMatrixUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    data = [item.model_dump() for item in body.matrix]
    matrix = await update_role_matrix(db, data)
    return ApiResponse(data=RoleMatrixResponse(
        matrix=[RoleMatrixItem(**item) for item in matrix]
    ))


@router.get("/matrix/export")
async def export_matrix(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    matrix = await get_role_matrix(db)
    lines = ["role_key,display_name,user_management,system_config,role_matrix"]
    for item in matrix:
        permissions = item["permissions"]
        lines.append(
            f'{item["role_key"]},{item["display_name"]},'
            f'{int(bool(permissions.get("user_management")))},'
            f'{int(bool(permissions.get("system_config")))},'
            f'{int(bool(permissions.get("role_matrix")))}'
        )
    return Response(
        content="\n".join(lines),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="role_matrix.csv"'},
    )
