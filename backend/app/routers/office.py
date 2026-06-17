from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import AppException, ConflictError, NotFound, ValidationError, PermissionDenied
from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.office import JsonPackageService, JsonVersionService, JsonPatchService
from app.services.file_share_service import check_file_access

router = APIRouter(prefix="/api/office", tags=["office"])

package_svc = JsonPackageService()
version_svc = JsonVersionService()
patch_svc = JsonPatchService()


async def _require_file_access(db: AsyncSession, file_id: int, user_id: int):
    """Check that user owns the file or has shared access to it."""
    from app.models.file import File
    file = await db.get(File, file_id)
    if not file or file.deleted:
        raise NotFound("File not found")
    access = await check_file_access(db, file_id, user_id)
    if not access["accessible"]:
        raise PermissionDenied("No permission to access this file")


@router.get("/status/{file_id}")
async def get_status(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_file_access(db, file_id, user.id)
    from app.models.file import File
    pkg = await package_svc.get_status(db, file_id)
    file = await db.get(File, file_id)
    return ApiResponse(data={
        "file_id": file_id,
        "file_name": f"{file.name}.{file.extension}" if file else "",
        "has_package": pkg is not None,
        "package_id": pkg.id if pkg else None,
        "current_version_id": pkg.current_version_id if pkg else None,
        "package_status": pkg.package_status if pkg else "not_generated",
        "summary": pkg.summary if pkg else None,
        "last_updated": str(pkg.updated_at) if pkg and pkg.updated_at else None,
    })


@router.post("/package")
async def create_package(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    await _require_file_access(db, file_id, user.id)
    result = await package_svc.create_package(db, file_id, user.id)
    return ApiResponse(data=result)


async def _require_package_access(db: AsyncSession, package_id: int, user_id: int):
    """Check that user can access the file linked to this package."""
    from app.models.office import FileJsonPackage
    pkg = await db.get(FileJsonPackage, package_id)
    if not pkg:
        raise NotFound("Package not found")
    await _require_file_access(db, pkg.file_id, user_id)
    return pkg


@router.get("/package/{package_id}")
async def read_package(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_package_access(db, package_id, user.id)
    result = await package_svc.read_package(db, package_id)
    if not result:
        raise NotFound("Package not found")
    return ApiResponse(data=result)


@router.get("/package/{package_id}/versions")
async def list_versions(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await _require_package_access(db, package_id, user.id)
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
    await _require_package_access(db, package_id, user.id)
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
        raise ValidationError(str(e))


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
    except AppException:
        raise
    except ValueError as e:
        raise ValidationError(str(e))
    except RuntimeError as e:
        raise ConflictError(str(e))


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
    except AppException:
        raise
    except ValueError as e:
        raise ValidationError(str(e))
    except RuntimeError as e:
        raise ConflictError(str(e))
