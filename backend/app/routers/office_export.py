import os
from fastapi import APIRouter, Depends
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.exceptions import NotFound, PermissionDenied
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.office import JsonPackageService, DocxService, ExcelService, PptxService
from app.services.file_share_service import check_file_access

router = APIRouter(prefix="/api/office", tags=["office-export"])

package_svc = JsonPackageService()


def _resolve_safe_path(storage_path: str) -> Path:
    """Resolve storage path safely, preventing path traversal."""
    from app.config import get_settings
    upload_dir = Path(get_settings().UPLOAD_DIR).resolve()
    full_path = (upload_dir / storage_path).resolve()
    if os.path.commonpath([str(upload_dir), str(full_path)]) != str(upload_dir):
        raise PermissionDenied("Invalid file path")
    return full_path


async def _require_file_access(db: AsyncSession, file_id: int, user_id: int):
    from app.models.file import File
    file = await db.get(File, file_id)
    if not file or file.deleted:
        raise NotFound("File not found")
    access = await check_file_access(db, file_id, user_id)
    if not access["accessible"]:
        raise PermissionDenied("No permission to access this file")


@router.post("/export/docx/{package_id}")
async def export_docx(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    from app.models.file import File
    from app.models.office import FileJsonPackage

    pkg = await db.get(FileJsonPackage, package_id)
    if not pkg:
        raise NotFound("Package not found")
    await _require_file_access(db, pkg.file_id, user.id)

    file = await db.get(File, pkg.file_id)
    if not file:
        raise NotFound("File not found")

    result = await package_svc.read_package(db, package_id)
    full_path = _resolve_safe_path(file.storage_path)

    svc = DocxService()
    await svc.export(str(full_path), result["json_content"])
    return ApiResponse(data={"message": "Document exported and overwritten successfully"})


@router.post("/export/excel/{package_id}")
async def export_excel(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    from app.models.file import File
    from app.models.office import FileJsonPackage

    pkg = await db.get(FileJsonPackage, package_id)
    if not pkg:
        raise NotFound("Package not found")
    await _require_file_access(db, pkg.file_id, user.id)

    file = await db.get(File, pkg.file_id)
    if not file:
        raise NotFound("File not found")

    result = await package_svc.read_package(db, package_id)
    full_path = _resolve_safe_path(file.storage_path)

    svc = ExcelService()
    await svc.export(str(full_path), result["json_content"])
    return ApiResponse(data={"message": "Excel exported and overwritten successfully"})


@router.post("/export/pptx/{package_id}")
async def export_pptx(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    from app.models.file import File
    from app.models.office import FileJsonPackage

    pkg = await db.get(FileJsonPackage, package_id)
    if not pkg:
        raise NotFound("Package not found")
    await _require_file_access(db, pkg.file_id, user.id)

    file = await db.get(File, pkg.file_id)
    if not file:
        raise NotFound("File not found")

    result = await package_svc.read_package(db, package_id)
    full_path = _resolve_safe_path(file.storage_path)

    svc = PptxService()
    await svc.export(str(full_path), result["json_content"])
    return ApiResponse(data={"message": "PPT exported and overwritten successfully"})
