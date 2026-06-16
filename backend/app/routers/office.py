from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.office import JsonPackageService, JsonVersionService, JsonPatchService

router = APIRouter(prefix="/api/office", tags=["office"])

package_svc = JsonPackageService()
version_svc = JsonVersionService()
patch_svc = JsonPatchService()


@router.get("/status/{file_id}")
async def get_status(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    from app.models.file import File
    pkg = await package_svc.get_status(db, file_id)
    file = await db.get(File, file_id)
    return ApiResponse(data={
        "file_id": file_id,
        "file_name": f"{file.name}.{file.extension}" if file else "",
        "has_package": pkg is not None,
        "package_id": pkg.id if pkg else None,
        "current_version_id": pkg.current_version_id if pkg else None,
        "package_status": pkg.package_status if pkg else "未生成",
        "summary": pkg.summary if pkg else None,
        "last_updated": str(pkg.updated_at) if pkg and pkg.updated_at else None,
    })


@router.post("/package")
async def create_package(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    try:
        result = await package_svc.create_package(db, file_id, user.id)
        return ApiResponse(data=result)
    except (ValueError, RuntimeError) as e:
        return ApiResponse(success=False, error=str(e))


@router.get("/package/{package_id}")
async def read_package(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await package_svc.read_package(db, package_id)
    if not result:
        return ApiResponse(success=False, error="包不存在")
    return ApiResponse(data=result)


@router.get("/package/{package_id}/versions")
async def list_versions(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    versions = await version_svc.list_versions(db, package_id)
    return ApiResponse(data=[
        {
            "id": v.id, "package_id": v.package_id,
            "version_number": v.version_number,
            "summary": v.summary, "creator_id": v.creator_id,
            "created_at": str(v.created_at) if v.created_at else None,
        }
        for v in versions
    ])


@router.get("/package/{package_id}/patches")
async def list_patches(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    patches = await patch_svc.list_patches(db, package_id)
    return ApiResponse(data=[
        {
            "id": p.id, "package_id": p.package_id,
            "source_version_id": p.source_version_id,
            "target_version_id": p.target_version_id,
            "operation_type": p.operation_type,
            "json_path": p.json_path,
            "risk_level": p.risk_level,
            "reason": p.reason, "patch_status": p.patch_status,
            "created_at": str(p.created_at) if p.created_at else None,
        }
        for p in patches
    ])


@router.post("/patch/preview")
async def preview_patch(
    body: dict,
    user: User = Depends(require_permission("viewer")),
):
    try:
        result = patch_svc.preview_patch(body.get("patch", {}))
        return ApiResponse(data=result)
    except ValueError as e:
        return ApiResponse(success=False, error=str(e))


@router.post("/patch/apply")
async def apply_patch(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    try:
        result = await patch_svc.apply_patch(
            db, body.get("patch", {}), body.get("package_id"), user.id
        )
        return ApiResponse(data=result)
    except (ValueError, RuntimeError) as e:
        return ApiResponse(success=False, error=str(e))


@router.post("/rollback")
async def rollback_version(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    try:
        result = await version_svc.rollback(
            db, body["package_id"], body["target_version_id"], user.id
        )
        return ApiResponse(data=result)
    except (ValueError, RuntimeError) as e:
        return ApiResponse(success=False, error=str(e))
