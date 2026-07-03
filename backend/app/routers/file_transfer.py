import hashlib
import io
import logging
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, UploadFile
from fastapi import File as FastAPIFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.file import (
    UploadResponse,
    UploadSessionCompleteRequest,
    UploadSessionCompleteResponse,
    UploadSessionCreateRequest,
    UploadSessionResponse,
)
from app.services import (
    file_preview_service,
    file_service,
    file_share_service,
    file_upload_service,
    file_upload_session_service,
)
from app.services.module_registry import call_capability

logger = logging.getLogger("v2.file_transfer")

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB 上传上限，防 OOM

TMP_DOWNLOAD_DIR = Path(get_settings().UPLOAD_DIR).resolve().parent / ".tmp_downloads"

router = APIRouter(prefix="/api/files", tags=["files"])


async def _emit_file_uploaded(file_id: int, user: User) -> None:
    try:
        from app.services.module_events import emit_module_event
        await emit_module_event(
            "file.uploaded",
            {"file_id": file_id},
            caller=f"user:{user.id}",
            caller_role=user.role,
        )
    except Exception as exc:
        logger.warning("File.uploaded event emission failed for file_id=%d: %s", file_id, exc)


@router.post("/upload")
async def upload(file: UploadFile = FastAPIFile(...), folder_id: int = Form(0), relative_path: str = Form(""), db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    if not file.filename:
        raise ValidationError("No file provided")
    # 流式写入临时文件，同时计算 md5
    tmp_dir = Path(get_settings().UPLOAD_DIR).resolve().parent / ".tmp_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(tmp_dir))
    total = 0
    md5 = hashlib.md5()
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise ValidationError(f"文件过大，超过 {MAX_UPLOAD_BYTES // (1024*1024)}MB 限制")
            os.write(tmp_fd, chunk)
            md5.update(chunk)
        if total == 0:
            raise ValidationError("Empty file")
    finally:
        os.close(tmp_fd)
    tmp_file_path = Path(tmp_path)
    md5_hex = md5.hexdigest()
    rp = relative_path.strip() if relative_path else None
    target_folder = folder_id if folder_id > 0 else None
    from app.services.file_upload_service import _detect_mime_by_header
    mime_type = _detect_mime_by_header(tmp_file_path, file.filename)
    result = await file_upload_service.upload_file_from_path(
        db, tmp_file_path, file.filename, user.id, target_folder, rp,
        md5_hex=md5_hex, mime_type=mime_type,
    )
    # Temp file cleanup
    try:
        tmp_file_path.unlink(missing_ok=True)
    except Exception:
        pass
    # ── 上传完成，尽力而为通知各模块（不阻塞上传） ──
    await _emit_file_uploaded(result["id"], user)
    return ApiResponse(data=UploadResponse(**result))


@router.post("/upload-sessions")
async def create_upload_session(
    payload: UploadSessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await file_upload_session_service.create_upload_session(
        db,
        filename=payload.filename,
        total_chunks=payload.total_chunks,
        owner_id=user.id,
        md5_expected=payload.md5_expected,
        expires_in_hours=payload.expires_in_hours,
    )
    return ApiResponse(data=UploadSessionResponse(**result))


@router.post("/upload-sessions/cleanup-expired")
async def cleanup_expired_upload_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    result = await file_upload_session_service.cleanup_expired_sessions(db)
    return ApiResponse(data=result)


@router.post("/upload-sessions/{session_id}/chunks")
async def upload_session_chunk(
    session_id: str,
    chunk_index: int = Form(...),
    chunk: UploadFile = FastAPIFile(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await file_upload_session_service.store_upload_chunk(
        db,
        session_id=session_id,
        owner_id=user.id,
        chunk_index=chunk_index,
        chunk_stream=chunk,
    )
    return ApiResponse(data=UploadSessionResponse(**result))


@router.post("/upload-sessions/{session_id}/complete")
async def complete_upload_session(
    session_id: str,
    payload: UploadSessionCompleteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await file_upload_session_service.complete_upload_session(
        db,
        session_id=session_id,
        owner_id=user.id,
        folder_id=payload.folder_id,
        relative_path=payload.relative_path,
    )
    await _emit_file_uploaded(result["file"]["id"], user)
    return ApiResponse(data=UploadSessionCompleteResponse(**result))


@router.post("/upload-sessions/{session_id}/abort")
async def abort_upload_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await file_upload_session_service.abort_upload_session(
        db,
        session_id=session_id,
        owner_id=user.id,
    )
    return ApiResponse(data=UploadSessionResponse(**result))


def _cleanup_temp_file(path: str) -> None:
    """Background task: delete temp file after response is sent."""
    try:
        p = Path(path)
        if p.exists():
            p.unlink(missing_ok=True)
            logger.debug("Cleaned up temp download file: %s", path)
    except Exception as e:
        logger.warning("Failed to clean up temp file %s: %s", path, e)


async def _try_compile_from_content_package(
    db: AsyncSession, file_id: int, user_id: int,
) -> dict | None:
    """Try to compile from ContentPackage. Returns None if no package found."""
    from app.models.content import ContentPackage
    from app.services.content.package_service import CONSUMABLE_PACKAGE_STATUSES
    result = await db.execute(
        select(ContentPackage).where(
            ContentPackage.source_file_id == file_id,
            ContentPackage.deleted.is_(False),
            ContentPackage.status.in_(CONSUMABLE_PACKAGE_STATUSES),
        ).order_by(ContentPackage.created_at.desc()).limit(1)
    )
    pkg = result.scalar_one_or_none()
    if not pkg:
        return None
    if pkg.package_type == "spreadsheet":
        return None

    try:
        caller = f"user:{user_id}"
        ext_map = {
            "document": "docx", "presentation": "pptx",
            "text": "txt", "spreadsheet": "xlsx",
        }
        target_format = ext_map.get(pkg.package_type, "docx")
        compile_result = await call_capability(
            "content", "compile",
            {"package_id": pkg.id, "target_format": target_format},
            caller=caller, caller_role="viewer",
        )
        if isinstance(compile_result, dict):
            data = compile_result.get("data", compile_result)
            if isinstance(data, dict) and data.get("file_path"):
                return {"file_path": data["file_path"], "filename": data["filename"]}
    except Exception as e:
        logger.warning("ContentPackage compile failed for file_id=%d: %s", file_id, e)
    return None


async def _try_compile_from_excel_engine(
    db: AsyncSession, file_id: int, user_id: int,
) -> dict | None:
    """Try to compile from excel-engine workbook. Returns None if no workbook found."""
    from app.models.file import File as FileModel
    state_key = f"knowledge_{file_id}"
    file_record = await db.get(FileModel, file_id)
    if not file_record:
        return None

    try:
        caller = f"user:{user_id}"
        compile_result = await call_capability(
            "excel-engine", "compile_xlsx",
            {"state_key": state_key},
            caller=caller, caller_role="viewer",
        )
        if isinstance(compile_result, dict):
            inner = compile_result.get("data", compile_result)
            if isinstance(inner, dict):
                fp = inner.get("file_path")
                if fp:
                    return {"file_path": fp, "filename": inner.get("filename", "export.xlsx")}
    except Exception:
        pass
    return None


@router.get("/download/{file_id}")
async def download(
    file_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    file = await file_service.get_file_record(db, file_id)
    if not file:
        raise NotFound("File not found")
    access = await file_share_service.check_file_access(db, file_id, user.id)
    if not access["accessible"]:
        raise PermissionDenied("Permission denied")

    # 1. Try ContentPackage compile
    compile_info = await _try_compile_from_content_package(db, file_id, user.id)
    if compile_info:
        TMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        background_tasks.add_task(_cleanup_temp_file, compile_info["file_path"])
        return FileResponse(
            path=compile_info["file_path"],
            media_type=_infer_mime(compile_info["filename"]),
            filename=compile_info["filename"],
        )

    # 2. Try excel-engine compile
    compile_info = await _try_compile_from_excel_engine(db, file_id, user.id)
    if compile_info:
        TMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        background_tasks.add_task(_cleanup_temp_file, compile_info["file_path"])
        return FileResponse(
            path=compile_info["file_path"],
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=compile_info["filename"],
        )

    # 3. Fallback: return original physical file
    safe_path = file_preview_service._resolve_storage_path(file)
    if not safe_path:
        raise NotFound("File on disk not found")
    full_name = f"{file.name}.{file.extension}" if file.extension else file.name
    return FileResponse(path=str(safe_path), media_type=file.mime_type or "application/octet-stream", filename=full_name)


@router.get("/download/{file_id}/original")
async def download_original(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """Force download of the original physical file, bypassing compile."""
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


def _infer_mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_map = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "txt": "text/plain",
        "md": "text/markdown",
    }
    return mime_map.get(ext, "application/octet-stream")


@router.post("/download-multiple")
async def download_multiple(file_ids: list[int], db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    buf = io.BytesIO()
    tmp_dir = TMP_DOWNLOAD_DIR
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cleanup_paths: list[str] = []
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fid in file_ids:
                file = await file_service.get_file_record(db, fid)
                if not file:
                    continue
                access = await file_share_service.check_file_access(db, fid, user.id)
                if not access["accessible"]:
                    continue
                arcname = f"{file.name}.{file.extension}" if file.extension else file.name

                # Try ContentPackage compile first - use compile filename for correct extension
                compile_info = await _try_compile_from_content_package(db, fid, user.id)
                if compile_info:
                    # Use the compile filename so extension matches the actual compiled format
                    compile_arcname = compile_info.get("filename", arcname)
                    zf.write(compile_info["file_path"], arcname=compile_arcname)
                    cleanup_paths.append(compile_info["file_path"])
                    continue

                # Try excel-engine compile
                compile_info = await _try_compile_from_excel_engine(db, fid, user.id)
                if compile_info:
                    compile_arcname = compile_info.get("filename", arcname)
                    zf.write(compile_info["file_path"], arcname=compile_arcname)
                    cleanup_paths.append(compile_info["file_path"])
                    continue

                # Fallback: original physical file
                safe_path = file_preview_service._resolve_storage_path(file)
                if not safe_path:
                    continue
                zf.write(str(safe_path), arcname=arcname)
    finally:
        for p in cleanup_paths:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
    buf.seek(0)
    return StreamingResponse(content=buf, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=files.zip"})


@router.get("/preview/{file_id}")
async def preview(file_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    result = await file_preview_service.preview_file(db, file_id, user.id)
    return ApiResponse(data=result)
