"""Zip selected files/folders for Finder compress download."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AppException, NotFound
from app.models.file import File, Folder


def _resolve_disk_path(storage_path: str | None) -> Path | None:
    if not storage_path:
        return None
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    full = (upload_dir / storage_path).resolve()
    try:
        if upload_dir not in full.parents and full != upload_dir:
            # also allow file directly under upload_dir
            if not str(full).startswith(str(upload_dir)):
                return None
    except Exception:
        return None
    return full if full.exists() and full.is_file() else None


async def _add_folder_to_zip(
    db: AsyncSession,
    *,
    zf: zipfile.ZipFile,
    folder: Folder,
    owner_id: int,
    prefix: str,
) -> None:
    base = f"{prefix}{folder.name}/"
    # ensure empty folder entry
    zf.writestr(base, b"")
    files = await db.execute(
        select(File).where(
            File.folder_id == folder.id,
            File.owner_id == owner_id,
            File.deleted.is_(False),
        )
    )
    for f in files.scalars().all():
        disk = _resolve_disk_path(f.storage_path)
        arc = f"{base}{f.name}{('.' + f.extension) if f.extension else ''}"
        if disk:
            zf.write(disk, arcname=arc)
        else:
            zf.writestr(arc, b"")
    subs = await db.execute(
        select(Folder).where(
            Folder.parent_id == folder.id,
            Folder.owner_id == owner_id,
            Folder.deleted.is_(False),
        )
    )
    for sub in subs.scalars().all():
        await _add_folder_to_zip(db, zf=zf, folder=sub, owner_id=owner_id, prefix=base)


async def build_zip_bytes(
    db: AsyncSession,
    *,
    owner_id: int,
    items: list[dict],
) -> tuple[bytes, str]:
    if not items:
        raise AppException("No items to compress", status_code=400)

    buf = io.BytesIO()
    added = 0
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for raw in items:
            item_type = str(raw.get("item_type") or raw.get("type") or "file")
            item_id = int(raw.get("id"))
            if item_type == "folder":
                folder = await db.get(Folder, item_id)
                if not folder or folder.deleted or folder.owner_id != owner_id:
                    continue
                await _add_folder_to_zip(db, zf=zf, folder=folder, owner_id=owner_id, prefix="")
                added += 1
            else:
                file = await db.get(File, item_id)
                if not file or file.deleted or file.owner_id != owner_id:
                    continue
                disk = _resolve_disk_path(file.storage_path)
                arc = f"{file.name}{('.' + file.extension) if file.extension else ''}"
                if disk:
                    zf.write(disk, arcname=arc)
                else:
                    zf.writestr(arc, b"")
                added += 1

    if added == 0:
        raise NotFound("No accessible items to compress")

    name = "归档.zip"
    if len(items) == 1:
        only = items[0]
        only_id = int(only.get("id"))
        only_type = str(only.get("item_type") or only.get("type") or "file")
        if only_type == "folder":
            folder = await db.get(Folder, only_id)
            if folder:
                name = f"{folder.name}.zip"
        else:
            file = await db.get(File, only_id)
            if file:
                name = f"{file.name}.zip"

    return buf.getvalue(), name
