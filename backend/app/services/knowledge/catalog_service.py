import asyncio
import hashlib
import mimetypes
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Catalog


CHANNEL_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".doc": "office", ".docx": "office",
    ".ppt": "office", ".pptx": "office",
    ".xls": "excel", ".xlsx": "excel", ".csv": "excel",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".gif": "image", ".bmp": "image", ".webp": "image", ".tiff": "image",
    ".mp4": "video", ".avi": "video", ".mov": "video",
    ".mkv": "video", ".flv": "video", ".wmv": "video", ".webm": "video",
}


def _compute_md5(file_path: str) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _detect_channel_type(file_path: str, mime_type: str = "") -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in CHANNEL_MAP:
        return CHANNEL_MAP[ext]
    if mime_type:
        if mime_type.startswith("image/"):
            return "image"
        if mime_type.startswith("video/"):
            return "video"
        if "pdf" in mime_type:
            return "pdf"
        if "word" in mime_type or "presentation" in mime_type:
            return "office"
        if "excel" in mime_type or "spreadsheet" in mime_type or "csv" in mime_type:
            return "excel"
    return "auto"


async def _async_file_stat(file_path: str) -> int:
    return await asyncio.to_thread(os.path.getsize, file_path)


class CatalogService:

    @staticmethod
    async def create_or_get(
        db: AsyncSession,
        file_path: str,
        owner_id: int,
    ) -> tuple[Catalog, bool]:
        exists = await asyncio.to_thread(os.path.exists, file_path)
        if not exists:
            raise FileNotFoundError(f"File not found: {file_path}")

        file_hash = await asyncio.to_thread(_compute_md5, file_path)
        result = await db.execute(
            select(Catalog).where(Catalog.file_hash == file_hash)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing, False

        file_name = os.path.basename(file_path)
        file_size = await _async_file_stat(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or ""
        channel_type = _detect_channel_type(file_path, mime_type)
        catalog = Catalog(
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            file_hash=file_hash,
            mime_type=mime_type,
            channel_type=channel_type,
            status="pending",
            owner_id=owner_id,
        )
        db.add(catalog)
        await db.commit()
        await db.refresh(catalog)
        return catalog, True

    @staticmethod
    async def update_status(
        db: AsyncSession,
        catalog_id: int,
        status: str,
        error: str | None = None,
    ):
        result = await db.execute(
            select(Catalog).where(Catalog.id == catalog_id)
        )
        catalog = result.scalar_one_or_none()
        if catalog:
            catalog.status = status
            if error:
                catalog.error = error
            await db.commit()
