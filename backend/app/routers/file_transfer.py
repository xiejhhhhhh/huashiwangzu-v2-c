import io
import zipfile
from fastapi import APIRouter, Depends, UploadFile, File as FastAPIFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.file import UploadResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services import file_upload_service, file_preview_service, file_service
from app.services import file_share_service

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload")
async def upload(file: UploadFile = FastAPIFile(...), folder_id: int = Form(0), relative_path: str = Form(""), db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    if not file.filename:
        raise ValidationError("No file provided")
    content = await file.read()
    if not content:
        raise ValidationError("Empty file")
    rp = relative_path.strip() if relative_path else None
    target_folder = folder_id if folder_id > 0 else None
    result = await file_upload_service.upload_file(db, io.BytesIO(content), file.filename, user.id, target_folder, rp)
    return ApiResponse(data=UploadResponse(**result))


@router.get("/download/{file_id}")
async def download(file_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    file = await file_service.get_file_record(db, file_id)
    if not file:
        raise NotFound("File not found")
    access = await file_share_service.check_file_access(db, file_id, user.id)
    if not access["accessible"]:
        raise PermissionDenied("Permission denied")
    safe_path = file_preview_service._resolve_storage_path(file)
    if not safe_path:
        raise NotFound("File on disk not found")
    full_name = f"{file.name}.{file.extension}" if file.extension else file.name
    return StreamingResponse(content=open(safe_path, "rb"), media_type=file.mime_type or "application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{full_name}"'})


@router.post("/download-multiple")
async def download_multiple(file_ids: list[int], db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fid in file_ids:
            file = await file_service.get_file_record(db, fid)
            if not file:
                continue
            access = await file_share_service.check_file_access(db, fid, user.id)
            if not access["accessible"]:
                continue
            safe_path = file_preview_service._resolve_storage_path(file)
            if not safe_path:
                continue
            arcname = f"{file.name}.{file.extension}" if file.extension else file.name
            zf.write(str(safe_path), arcname=arcname)
    buf.seek(0)
    return StreamingResponse(content=buf, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=files.zip"})


@router.get("/preview/{file_id}")
async def preview(file_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    result = await file_preview_service.preview_file(db, file_id, user.id)
    return ApiResponse(data=result)
