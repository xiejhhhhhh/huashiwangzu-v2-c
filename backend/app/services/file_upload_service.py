import hashlib
import os
import magic
from pathlib import Path
from typing import BinaryIO
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.file import Folder, File
from app.core.exceptions import NotFound, AppException
from app.config import get_settings

settings = get_settings()
UPLOAD_ROOT = Path(settings.UPLOAD_DIR).resolve()


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

    file_bytes = file_obj.read()
    md5_hash = hashlib.md5(file_bytes).hexdigest()

    if relative_path:
        target_folder_id = await _ensure_folder_path(db, relative_path, owner_id, target_folder_id)

    # Check name conflict in target directory (after path resolution)
    existing_name = await db.execute(
        select(File).where(
            File.name == name_part,
            File.extension == ext_part,
            File.folder_id == target_folder_id,
            File.owner_id == owner_id,
            File.deleted == False,
        )
    )
    if existing_name.scalar_one_or_none():
        raise AppException("A file with the same name already exists in this directory", status_code=409)

    mime_type = _detect_mime(file_bytes, ext_part)

    # Content-addressable storage path: {md5[0:2]}/{md5[2:4]}/{md5}.{ext}
    content_path = f"{md5_hash[:2]}/{md5_hash[2:4]}/{md5_hash}.{ext_part}" if ext_part else f"{md5_hash[:2]}/{md5_hash[2:4]}/{md5_hash}"
    abs_content_path = UPLOAD_ROOT / content_path

    # Check if content already exists on disk (search across all users for same md5_hash)
    existing_content = await db.execute(
        select(File).where(File.md5_hash == md5_hash, File.deleted == False).limit(1)
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
        await db.commit()
        await db.refresh(new_file)

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
    parts = [p for p in relative_path.split("/") if p]
    current_parent = parent_id
    for part in parts:
        existing = await db.execute(
            select(Folder).where(
                Folder.name == part,
                Folder.parent_id == current_parent,
                Folder.owner_id == owner_id,
                Folder.deleted == False,
            )
        )
        folder = existing.scalar_one_or_none()
        if not folder:
            folder = Folder(name=part, parent_id=current_parent, owner_id=owner_id)
            db.add(folder)
            await db.flush()
        current_parent = folder.id
    return current_parent


def _detect_mime(data: bytes, ext: str) -> str:
    try:
        return magic.from_buffer(data, mime=True)
    except Exception:
        mime_map = {
            "txt": "text/plain", "md": "text/markdown", "html": "text/html",
            "css": "text/css", "js": "application/javascript", "json": "application/json",
            "csv": "text/csv", "xml": "application/xml", "pdf": "application/pdf",
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "svg": "image/svg+xml",
        }
        return mime_map.get(ext, "application/octet-stream")
