"""Content read/write operations for docs-open module."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.config import get_settings
from app.core.exceptions import AppException

from .embed import _get_doc_type


async def _read_content(db: AsyncSession, file: File, ext: str, user_role: str = "editor") -> dict:
    """Read document content as structured JSON based on type."""
    settings = get_settings()
    storage_root = Path(settings.UPLOAD_DIR).resolve()
    full_path = (storage_root / file.storage_path).resolve()

    if ext in ("txt", "md", "json", "yaml", "yml", "xml", "ini", "cfg", "log"):
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return {"content": text, "format": "text", "extension": ext}

    if ext in ("xlsx", "xls"):
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "excel-engine", "parse",
                {"file_id": file.id},
                caller=f"user:{file.owner_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "excel-json", "extension": ext}
        except Exception as e:
            return {"error": f"Failed to parse xlsx: {e}", "format": "error", "extension": ext}

    if ext == "csv":
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        import csv, io
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        return {"content": rows, "format": "csv-json", "extension": ext}

    if ext == "pdf":
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "pdf-parser", "parse",
                {"file_id": file.id},
                caller=f"user:{file.owner_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "parsed-json", "extension": ext}
        except Exception as e:
            return {"error": f"Failed to parse pdf: {e}", "format": "error", "extension": ext}

    if ext == "docx":
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "docx-parser", "parse",
                {"file_id": file.id},
                caller=f"user:{file.owner_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "parsed-json", "extension": ext}
        except Exception as e:
            return {"error": f"Failed to parse docx: {e}", "format": "error", "extension": ext}

    if ext == "pptx":
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "pptx-parser", "parse",
                {"file_id": file.id},
                caller=f"user:{file.owner_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "parsed-json", "extension": ext}
        except Exception as e:
            return {"error": f"Failed to parse pptx: {e}", "format": "error", "extension": ext}

    return {"content": None, "format": "binary", "extension": ext}


async def _write_content(db: AsyncSession, file: File, ext: str, content: dict | list | str, user_role: str = "editor") -> None:
    """Write structured content back to a document.

    Uses framework replace_file_content (content-addressed) instead of
    direct disk overwrite to preserve content-addressable dedup integrity.
    """
    from app.services.file_upload_service import replace_file_content

    if ext in ("txt", "md", "json", "yaml", "yml", "xml", "ini", "cfg", "log"):
        text = content if isinstance(content, str) else str(content)
        await replace_file_content(db, file.id, file.owner_id, text.encode("utf-8"))

    elif ext in ("xlsx", "xls"):
        try:
            from app.services.module_registry import call_capability
            json_str = __import__("json").dumps(content, ensure_ascii=False)
            await call_capability(
                "office-gen", "xlsx",
                {"filename": file.name, "content": json_str},
                caller=f"user:{file.owner_id}",
                caller_role="admin",
            )
        except Exception as e:
            raise AppException(f"Failed to write xlsx: {e}", status_code=500)

    elif ext in ("docx",):
        try:
            from app.services.module_registry import call_capability
            await call_capability(
                "office-gen", "docx",
                {"filename": file.name, "content": content},
                caller=f"user:{file.owner_id}",
                caller_role="admin",
            )
        except Exception as e:
            raise AppException(f"Failed to write docx: {e}", status_code=500)

    elif ext == "csv":
        text = content if isinstance(content, str) else str(content)
        await replace_file_content(db, file.id, file.owner_id, text.encode("utf-8"))

    else:
        raise AppException(f"Writing to {ext} is not supported yet", status_code=400)
