from fastapi import APIRouter, Depends
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.office import JsonPackageService, DocxService, ExcelService, PptxService

router = APIRouter(prefix="/api/office", tags=["office-export"])

package_svc = JsonPackageService()


@router.post("/export/docx/{package_id}")
async def export_docx(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    from app.models.file import File
    from app.models.office import FileJsonPackage
    from app.config import get_settings

    pkg = await db.get(FileJsonPackage, package_id)
    if not pkg:
        return ApiResponse(success=False, error="包不存在")
    file = await db.get(File, pkg.file_id)
    if not file:
        return ApiResponse(success=False, error="文件不存在")

    result = await package_svc.read_package(db, package_id)
    full_path = str(Path(get_settings().UPLOAD_DIR) / file.storage_path)

    svc = DocxService()
    await svc.export(full_path, result["json_content"])
    return ApiResponse(data={"message": "文档导出成功，已覆盖原文件"})


@router.post("/export/excel/{package_id}")
async def export_excel(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    from app.models.file import File
    from app.models.office import FileJsonPackage
    from app.config import get_settings

    pkg = await db.get(FileJsonPackage, package_id)
    if not pkg:
        return ApiResponse(success=False, error="包不存在")
    file = await db.get(File, pkg.file_id)
    if not file:
        return ApiResponse(success=False, error="文件不存在")

    result = await package_svc.read_package(db, package_id)
    full_path = str(Path(get_settings().UPLOAD_DIR) / file.storage_path)

    svc = ExcelService()
    await svc.export(full_path, result["json_content"])
    return ApiResponse(data={"message": "Excel 导出成功，已覆盖原文件"})


@router.post("/export/pptx/{package_id}")
async def export_pptx(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    from app.models.file import File
    from app.models.office import FileJsonPackage
    from app.config import get_settings

    pkg = await db.get(FileJsonPackage, package_id)
    if not pkg:
        return ApiResponse(success=False, error="包不存在")
    file = await db.get(File, pkg.file_id)
    if not file:
        return ApiResponse(success=False, error="文件不存在")

    result = await package_svc.read_package(db, package_id)
    full_path = str(Path(get_settings().UPLOAD_DIR) / file.storage_path)

    svc = PptxService()
    await svc.export(full_path, result["json_content"])
    return ApiResponse(data={"message": "PPT 导出成功，已覆盖原文件"})
