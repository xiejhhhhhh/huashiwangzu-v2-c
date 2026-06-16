import hashlib
import os
import magic
from pathlib import Path
from typing import BinaryIO
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.file import Folder, File
from app.core.exceptions import NotFound
from app.config import get_settings

settings = get_settings()
UPLOAD_ROOT = Path(settings.UPLOAD_DIR)


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

    file_bytes = file_obj.read()
    md5_hash = hashlib.md5(file_bytes).hexdigest()

    existing = await db.execute(
        select(File).where(File.md5 == md5_hash, File.deleted == False)
    )
    existing_file = existing.scalar_one_or_none()
    if existing_file:
        return {
            "exists": True,
            "id": existing_file.id,
            "name": existing_file.name,
            "extension": existing_file.extension,
        }

    if relative_path:
        target_folder_id = await _ensure_folder_path(db, relative_path, owner_id, target_folder_id)

    mime_type = _detect_mime(file_bytes, ext_part)

    new_file = File(
        name=name_part,
        extension=ext_part or "",
        size=len(file_bytes),
        folder_id=target_folder_id,
        owner_id=owner_id,
        storage_path="",
        mime_type=mime_type,
        md5=md5_hash,
        deleted=False,
    )
    db.add(new_file)
    await db.flush()

    storage_name = f"{new_file.id}.{ext_part}" if ext_part else f"{new_file.id}"
    relative_storage = f"source/{storage_name}"
    abs_dir = UPLOAD_ROOT / "source"
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = abs_dir / storage_name
    abs_path.write_bytes(file_bytes)

    new_file.storage_path = relative_storage
    new_file.size = abs_path.stat().st_size
    await db.commit()
    await db.refresh(new_file)

    return {
        "exists": False,
        "id": new_file.id,
        "name": new_file.name,
        "extension": new_file.extension,
        "size": new_file.size,
        "mime_type": new_file.mime_type,
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
