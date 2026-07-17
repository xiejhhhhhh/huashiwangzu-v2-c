import hashlib
import os
import shutil
from pathlib import Path
from typing import BinaryIO

import magic
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.contracts.content_hash import source_sha256_from_bytes, source_sha256_from_path
from app.core.exceptions import AppException, NotFound
from app.models.file import File, Folder

settings = get_settings()
UPLOAD_ROOT = Path(settings.UPLOAD_DIR).resolve()


async def _ensure_upload_derivatives(db: AsyncSession, file_id: int) -> None:
    try:
        from app.services.image_derivative_service import ensure_standard_image_derivative

        await ensure_standard_image_derivative(db, file_id)
    except Exception:
        # Upload must not fail because an optional preview/work-image derivative failed.
        pass


async def upload_file(
    db: AsyncSession,
    file_obj: BinaryIO,
    filename: str,
    owner_id: int,
    folder_id: int | None = None,
    relative_path: str | None = None,
) -> dict:
    original_name = filename
    name_part, ext_part = os.path.splitext(original_name)
    ext_part = ext_part.lstrip(".").lower()

    target_folder_id = folder_id if (folder_id and folder_id > 0) else None
    if target_folder_id:
        folder = await db.get(Folder, target_folder_id)
        if not folder or folder.deleted:
            raise NotFound("Target folder not found")
        if folder.owner_id != owner_id:
            raise AppException("Access denied: target folder does not belong to current user", status_code=403)

    from app.services.content.source_revision import record_file_revision

    file_bytes = file_obj.read()
    md5_hash = hashlib.md5(file_bytes).hexdigest()
    source_sha256 = source_sha256_from_bytes(file_bytes)

    if relative_path:
        target_folder_id = await _ensure_folder_path(db, relative_path, owner_id, target_folder_id)

    # Check name conflict in target directory (after path resolution)
    existing_name = await db.execute(
        select(File)
        .where(
            File.name == name_part,
            File.extension == ext_part,
            File.folder_id == target_folder_id,
            File.owner_id == owner_id,
            File.deleted.is_(False),
        )
        .order_by(File.id.asc())
        .limit(1)
    )
    if existing_name.scalar_one_or_none():
        raise AppException("A file with the same name already exists in this directory", status_code=409)

    mime_type = _detect_mime(file_bytes, ext_part)

    # Content-addressable storage path: {md5[0:2]}/{md5[2:4]}/{md5}.{ext}
    content_path = f"{md5_hash[:2]}/{md5_hash[2:4]}/{md5_hash}.{ext_part}" if ext_part else f"{md5_hash[:2]}/{md5_hash[2:4]}/{md5_hash}"
    abs_content_path = UPLOAD_ROOT / content_path

    # Check if content already exists on disk (search across all users for same md5_hash)
    existing_content = await db.execute(
        select(File).where(File.md5_hash == md5_hash, File.deleted.is_(False)).limit(1)
    )
    existing_file = existing_content.scalar_one_or_none()

    deduplicated = False
    if existing_file and abs_content_path.exists():
        # Content already on disk — create own record, share storage_path, increment ref_count
        deduplicated = True
        new_file = File(
            name=name_part,
            extension=ext_part or "",
            size=len(file_bytes),
            folder_id=target_folder_id,
            owner_id=owner_id,
            storage_path=existing_file.storage_path,
            mime_type=mime_type,
            md5_hash=md5_hash,
            ref_count=1,
            deleted=False,
        )
        db.add(new_file)
        await db.flush()
        # 记录首个不可变字节血缘 Revision（origin=user_import），并指向 current
        await record_file_revision(
            db, new_file, sha256=source_sha256, origin="user_import",
            created_by=owner_id,
        )
        # Increment ref_count on the existing content-bearing record
        await db.execute(
            update(File).where(File.id == existing_file.id).values(ref_count=File.ref_count + 1)
        )
        await db.commit()
        await db.refresh(new_file)
    else:
        # New content — write to disk first, then create DB record
        abs_content_path.parent.mkdir(parents=True, exist_ok=True)
        abs_content_path.write_bytes(file_bytes)

        new_file = File(
            name=name_part,
            extension=ext_part or "",
            size=len(file_bytes),
            folder_id=target_folder_id,
            owner_id=owner_id,
            storage_path=content_path,
            mime_type=mime_type,
            md5_hash=md5_hash,
            ref_count=1,
            deleted=False,
        )
        db.add(new_file)
        await db.flush()
        await record_file_revision(
            db, new_file, sha256=source_sha256, origin="user_import",
            created_by=owner_id,
        )
        await db.commit()
        await db.refresh(new_file)

    await _ensure_upload_derivatives(db, new_file.id)

    return {
        "id": new_file.id,
        "name": new_file.name,
        "extension": new_file.extension,
        "size": new_file.size,
        "mime_type": new_file.mime_type,
        "deduplicated": deduplicated,
    }


async def _ensure_folder_path(
    db: AsyncSession, relative_path: str, owner_id: int, parent_id: int | None
) -> int:
    from app.services.file_service import _lock_folder_namespace

    parts = [p for p in relative_path.split("/") if p]
    current_parent = parent_id
    for part in parts:
        await _lock_folder_namespace(db, owner_id, current_parent)
        existing = await db.execute(
            select(Folder)
            .where(
                Folder.name == part,
                Folder.parent_id == current_parent,
                Folder.owner_id == owner_id,
                Folder.deleted.is_(False),
            )
            .order_by(Folder.id.asc())
            .limit(1)
        )
        folder = existing.scalar_one_or_none()
        if not folder:
            folder = Folder(name=part, parent_id=current_parent, owner_id=owner_id)
            db.add(folder)
            await db.flush()
        current_parent = folder.id
    return current_parent


async def replace_file_content(
    db: AsyncSession,
    file_id: int,
    user_id: int,
    content: bytes,
) -> dict:
    """Replace a file's content with new bytes (content-addressable).

    Writes new content to a new content-addressed path, updates the File record's
    storage_path/size/md5_hash, and maintains ref_count (old content cleaned up
    when its ref_count reaches zero).
    """
    file = await db.get(File, file_id)
    if not file or file.deleted:
        raise NotFound("File not found")
    from app.services.file_service import check_file_write_access

    await check_file_write_access(db, file_id, user_id)

    from app.services.content.source_revision import record_file_revision

    old_storage_path = file.storage_path
    new_md5 = hashlib.md5(content).hexdigest()
    new_source_sha256 = source_sha256_from_bytes(content)
    ext = file.extension or ""
    new_content_path = f"{new_md5[:2]}/{new_md5[2:4]}/{new_md5}.{ext}" if ext else f"{new_md5[:2]}/{new_md5[2:4]}/{new_md5}"
    abs_new_path = UPLOAD_ROOT / new_content_path

    # Check if new content already exists on disk
    existing = await db.execute(
        select(File).where(File.md5_hash == new_md5, File.deleted.is_(False)).limit(1)
    )
    existing_file = existing.scalar_one_or_none()

    if existing_file and abs_new_path.exists():
        file.storage_path = existing_file.storage_path
        await db.execute(
            update(File).where(File.id == existing_file.id).values(ref_count=File.ref_count + 1)
        )
    else:
        abs_new_path.parent.mkdir(parents=True, exist_ok=True)
        abs_new_path.write_bytes(content)
        file.storage_path = new_content_path

    file.size = len(content)
    file.md5_hash = new_md5
    await db.flush()

    # 内容替换 → 新增一条 external_replace Revision（revision_no 递增），并指向 current
    await record_file_revision(
        db, file, sha256=new_source_sha256, origin="external_replace",
        created_by=user_id,
    )

    # Decrement ref_count of old content
    if old_storage_path and old_storage_path != file.storage_path:
        old_records = await db.execute(
            select(File).where(
                File.storage_path == old_storage_path,
                File.deleted.is_(False),
            )
        )
        old_files = old_records.scalars().all()
        if len(old_files) == 1 and old_files[0].id == file.id:
            pass
        else:
            for of in old_files:
                if of.id != file.id:
                    await db.execute(
                        update(File).where(File.id == of.id).values(ref_count=File.ref_count - 1)
                    )
                    break

    # Mark associated ContentPackage as stale
    try:
        from sqlalchemy import update as sa_update

        from app.models.content import ContentPackage
        await db.execute(
            sa_update(ContentPackage)
            .where(
                ContentPackage.source_file_id == file_id,
                ContentPackage.deleted.is_(False),
            )
            .values(status="stale")
        )
    except Exception:
        pass

    await db.commit()
    await db.refresh(file)

    await _ensure_upload_derivatives(db, file.id)

    return {
        "id": file.id,
        "name": file.name,
        "size": file.size,
        "md5_hash": file.md5_hash,
        "storage_path": file.storage_path,
    }


async def upload_file_from_path(
    db: AsyncSession,
    file_path: Path,
    filename: str,
    owner_id: int,
    folder_id: int | None = None,
    relative_path: str | None = None,
    md5_hex: str | None = None,
    mime_type: str | None = None,
) -> dict:
    """Upload a file from a local temp path (stream-friendly).

    Uses pre-computed md5 and mime if provided, otherwise computes them.
    Atomic rename from temp to final content-addressed path.
    """
    original_name = filename
    name_part, ext_part = os.path.splitext(original_name)
    ext_part = ext_part.lstrip(".").lower()

    target_folder_id = folder_id if (folder_id and folder_id > 0) else None
    if target_folder_id:
        folder = await db.get(Folder, target_folder_id)
        if not folder or folder.deleted:
            raise NotFound("Target folder not found")
        if folder.owner_id != owner_id:
            raise AppException("Access denied: target folder does not belong to current user", status_code=403)

    from app.services.content.source_revision import record_file_revision

    if md5_hex:
        md5_hash = md5_hex
    else:
        md5_hash = hashlib.md5(file_path.read_bytes()).hexdigest()

    file_size = file_path.stat().st_size
    # 真源字节 SHA-256（流式，趁临时文件还在原地、未 rename）
    source_sha256 = source_sha256_from_path(str(file_path))

    if relative_path:
        target_folder_id = await _ensure_folder_path(db, relative_path, owner_id, target_folder_id)

    existing_name = await db.execute(
        select(File)
        .where(
            File.name == name_part,
            File.extension == ext_part,
            File.folder_id == target_folder_id,
            File.owner_id == owner_id,
            File.deleted.is_(False),
        )
        .order_by(File.id.asc())
        .limit(1)
    )
    if existing_name.scalar_one_or_none():
        raise AppException("A file with the same name already exists in this directory", status_code=409)

    if mime_type is None:
        if ext_part:
            mime_type = _detect_mime(b"", ext_part)
        else:
            mime_type = "application/octet-stream"

    content_path = f"{md5_hash[:2]}/{md5_hash[2:4]}/{md5_hash}.{ext_part}" if ext_part else f"{md5_hash[:2]}/{md5_hash[2:4]}/{md5_hash}"
    abs_content_path = UPLOAD_ROOT / content_path

    existing_content = await db.execute(
        select(File).where(File.md5_hash == md5_hash, File.deleted.is_(False)).limit(1)
    )
    existing_file = existing_content.scalar_one_or_none()

    deduplicated = False
    if existing_file and abs_content_path.exists():
        deduplicated = True
        new_file = File(
            name=name_part, extension=ext_part or "", size=file_size,
            folder_id=target_folder_id, owner_id=owner_id,
            storage_path=existing_file.storage_path,
            mime_type=mime_type, md5_hash=md5_hash, ref_count=1, deleted=False,
        )
        db.add(new_file)
        await db.flush()
        await record_file_revision(
            db, new_file, sha256=source_sha256, origin="user_import",
            created_by=owner_id,
        )
        await db.execute(
            update(File).where(File.id == existing_file.id).values(ref_count=File.ref_count + 1)
        )
        await db.commit()
        await db.refresh(new_file)
    else:
        abs_content_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            file_path.rename(abs_content_path)
        except OSError:
            shutil.copy2(file_path, abs_content_path)
            try:
                file_path.unlink()
            except OSError:
                pass
        new_file = File(
            name=name_part, extension=ext_part or "", size=file_size,
            folder_id=target_folder_id, owner_id=owner_id,
            storage_path=content_path, mime_type=mime_type,
            md5_hash=md5_hash, ref_count=1, deleted=False,
        )
        db.add(new_file)
        await db.flush()
        await record_file_revision(
            db, new_file, sha256=source_sha256, origin="user_import",
            created_by=owner_id,
        )
        await db.commit()
        await db.refresh(new_file)

    await _ensure_upload_derivatives(db, new_file.id)

    return {
        "id": new_file.id, "name": new_file.name,
        "extension": new_file.extension, "size": new_file.size,
        "mime_type": new_file.mime_type, "deduplicated": deduplicated,
    }


def _detect_mime_by_header(file_path: Path, filename: str) -> str:
    """Read only file header (first 2KB) for MIME detection."""
    try:
        header = file_path.read_bytes()[:2048]
        return magic.from_buffer(header, mime=True)
    except Exception:
        _, ext = os.path.splitext(filename)
        ext = ext.lstrip(".").lower()
        mime_map = {
            "txt": "text/plain", "md": "text/markdown", "html": "text/html",
            "css": "text/css", "js": "application/javascript", "json": "application/json",
            "csv": "text/csv", "xml": "application/xml", "pdf": "application/pdf",
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "jpe": "image/jpeg", "jfif": "image/jpeg", "gif": "image/gif",
            "svg": "image/svg+xml", "webp": "image/webp", "bmp": "image/bmp",
            "ico": "image/x-icon", "tif": "image/tiff", "tiff": "image/tiff",
            "avif": "image/avif",
        }
        return mime_map.get(ext, "application/octet-stream")


def _detect_mime(data: bytes, ext: str) -> str:
    try:
        return magic.from_buffer(data, mime=True)
    except Exception:
        mime_map = {
            "txt": "text/plain", "md": "text/markdown", "html": "text/html",
            "css": "text/css", "js": "application/javascript", "json": "application/json",
            "csv": "text/csv", "xml": "application/xml", "pdf": "application/pdf",
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "jpe": "image/jpeg", "jfif": "image/jpeg", "gif": "image/gif",
            "svg": "image/svg+xml", "webp": "image/webp", "bmp": "image/bmp",
            "ico": "image/x-icon", "tif": "image/tiff", "tiff": "image/tiff",
            "avif": "image/avif",
        }
        return mime_map.get(ext, "application/octet-stream")
