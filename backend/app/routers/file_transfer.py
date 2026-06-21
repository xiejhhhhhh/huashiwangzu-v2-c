import logging
import io
import zipfile
from fastapi import APIRouter, Depends, UploadFile, File as FastAPIFile, Form
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.file import UploadResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services import file_upload_service, file_preview_service, file_service
from app.services import file_share_service

logger = logging.getLogger("v2.file_transfer")

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB 上传上限，防 OOM

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload")
async def upload(file: UploadFile = FastAPIFile(...), folder_id: int = Form(0), relative_path: str = Form(""), db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    if not file.filename:
        raise ValidationError("No file provided")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 每次 1MB
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise ValidationError(f"文件过大，超过 {MAX_UPLOAD_BYTES // (1024*1024)}MB 限制")
        chunks.append(chunk)
    if total == 0:
        raise ValidationError("Empty file")
    content = b"".join(chunks)
    rp = relative_path.strip() if relative_path else None
    target_folder = folder_id if folder_id > 0 else None
    result = await file_upload_service.upload_file(db, io.BytesIO(content), file.filename, user.id, target_folder, rp)
    # ── 上传完成，尽力而为通知知识库登记分析（不阻塞上传） ──
    try:
        from app.services.module_registry import call_capability
        await call_capability(
            "knowledge", "ingest",
            {"file_id": result["id"]},
            caller=f"user:{user.id}",
            caller_role=user.role,
        )
    except Exception as exc:
        logger.warning("Knowledge ingest skipped for file_id=%d: %s", result["id"], exc)
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
    return FileResponse(path=str(safe_path), media_type=file.mime_type or "application/octet-stream", filename=full_name)


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
