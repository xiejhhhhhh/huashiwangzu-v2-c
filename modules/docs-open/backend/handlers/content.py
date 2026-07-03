"""Content read/write operations for docs-open module."""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.core.exceptions import AppException, NotFound
from app.models.file import File
from sqlalchemy.ext.asyncio import AsyncSession

TEXT_EXTENSIONS = {"txt", "md", "json", "yaml", "yml", "xml", "ini", "cfg", "log"}


def _resolve_storage_path(file: File) -> Path:
    settings = get_settings()
    storage_root = Path(settings.UPLOAD_DIR).resolve()
    if not file.storage_path:
        raise NotFound("File not found on disk")
    full_path = (storage_root / file.storage_path).resolve()
    if (
        __import__("os").path.commonpath([str(storage_root), str(full_path)]) != str(storage_root)
        or not full_path.exists()
    ):
        raise NotFound("File not found on disk")
    return full_path


async def _read_content(
    db: AsyncSession,
    file: File,
    ext: str,
    user_id: int,
    user_role: str = "editor",
) -> dict:
    """Read document content as structured JSON based on type."""
    full_path = _resolve_storage_path(file)

    if ext in TEXT_EXTENSIONS:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return {"content": text, "format": "text", "extension": ext}

    if ext in ("xlsx", "xls"):
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "excel-engine", "parse",
                {"file_id": file.id},
                caller=f"user:{user_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "excel-json", "extension": ext}
        except Exception as e:
            raise AppException(f"Failed to parse xlsx: {e}", status_code=502) from e

    if ext == "csv":
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        import csv
        import io

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        return {"content": rows, "format": "csv-json", "extension": ext}

    if ext == "pdf":
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "pdf-parser", "parse",
                {"file_id": file.id},
                caller=f"user:{user_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "parsed-json", "extension": ext}
        except Exception as e:
            raise AppException(f"Failed to parse pdf: {e}", status_code=502) from e

    if ext == "docx":
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "docx-parser", "parse",
                {"file_id": file.id},
                caller=f"user:{user_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "parsed-json", "extension": ext}
        except Exception as e:
            raise AppException(f"Failed to parse docx: {e}", status_code=502) from e

    if ext == "pptx":
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "pptx-parser", "parse",
                {"file_id": file.id},
                caller=f"user:{user_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "parsed-json", "extension": ext}
        except Exception as e:
            raise AppException(f"Failed to parse pptx: {e}", status_code=502) from e

    return {"content": None, "format": "binary", "extension": ext}


async def _write_content(
    db: AsyncSession,
    file: File,
    ext: str,
    content: dict | list | str,
    user_id: int,
    user_role: str = "editor",
) -> None:
    """Write structured content back to a document.

    Uses framework replace_file_content (content-addressed) instead of
    direct disk overwrite to preserve content-addressable dedup integrity.
    """
    from app.services.file_upload_service import replace_file_content

    if ext in TEXT_EXTENSIONS:
        text = content if isinstance(content, str) else str(content)
        await replace_file_content(db, file.id, user_id, text.encode("utf-8"))

    elif ext in ("xlsx", "xls"):
        raise AppException("Writing xlsx through docs-open is not supported yet", status_code=400)

    elif ext in ("docx",):
        raise AppException("Writing docx through docs-open is not supported yet", status_code=400)

    elif ext == "csv":
        text = content if isinstance(content, str) else str(content)
        await replace_file_content(db, file.id, user_id, text.encode("utf-8"))

    else:
        raise AppException(f"Writing to {ext} is not supported yet", status_code=400)
