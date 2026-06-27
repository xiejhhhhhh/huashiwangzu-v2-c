"""FastAPI router for text-parser module.

Registers the parse capability with the framework's cross-module registry.
"""
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability

router = APIRouter(prefix="/api/text-parser", tags=["text-parser"])


class ParseRequest(BaseModel):
    file_id: int


def _resolve_user_id(caller: str) -> int:
    from app.core.exceptions import PermissionDenied

    try:
        prefix, raw_id = caller.split(":", 1)
        if prefix == "user":
            return int(raw_id)
    except (TypeError, ValueError):
        pass
    raise PermissionDenied("Invalid caller")


async def _parse(params: dict, caller: str) -> dict:
    """Parse TXT/MD file into unified content blocks."""
    file_id = int(params.get("file_id", 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.config import get_settings
    from app.core.exceptions import NotFound, ValidationError, AppException
    from app.services.file_service import check_file_access
    from pathlib import Path

    allowed = {"txt", "md", "markdown", "text", "log"}
    user_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        ext = (file.extension or "").lower()
        if ext not in allowed:
            raise ValidationError("Unsupported format '%s'. Allowed: %s" % (ext, ", ".join(sorted(allowed))))
        if not file.storage_path:
            raise NotFound("File storage path is empty")
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
            raise AppException("Unsafe file storage path", status_code=400)
        if not full_path.exists() or not full_path.is_file():
            raise NotFound("File on disk not found")

        ALLOWED_ENCS = ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"]
        raw = full_path.read_bytes()
        content = None
        for enc in ALLOWED_ENCS:
            try:
                content = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if content is None:
            content = raw.decode("utf-8", errors="replace")

        content = content.replace("\r\n", "\n").replace("\r", "\n")
        lines = content.splitlines(keepends=False)
        blocks = []
        is_md = ext in ("md", "markdown")

        if is_md:
            para_lines = []
            in_code_block = False
            for line in lines:
                if line.startswith("```"):
                    if para_lines:
                        text = "\n".join(para_lines).strip()
                        if text:
                            blocks.append({"type": "段落", "text": text, "page": None, "resource_ref": None})
                        para_lines = []
                    in_code_block = not in_code_block
                    blocks.append({"type": "段落", "text": line, "page": None, "resource_ref": None})
                    continue
                if in_code_block:
                    blocks.append({"type": "段落", "text": line, "page": None, "resource_ref": None})
                    continue
                if line.startswith("#"):
                    if para_lines:
                        text = "\n".join(para_lines).strip()
                        if text:
                            blocks.append({"type": "段落", "text": text, "page": None, "resource_ref": None})
                        para_lines = []
                    title_text = line.lstrip("#").strip()
                    blocks.append({"type": "标题", "text": title_text, "page": None, "resource_ref": None})
                    continue
                if line.strip() == "":
                    if para_lines:
                        text = "\n".join(para_lines).strip()
                        if text:
                            blocks.append({"type": "段落", "text": text, "page": None, "resource_ref": None})
                        para_lines = []
                    continue
                para_lines.append(line)
            if para_lines:
                text = "\n".join(para_lines).strip()
                if text:
                    blocks.append({"type": "段落", "text": text, "page": None, "resource_ref": None})
        else:
            para_lines = []
            for line in lines:
                if line.strip() == "":
                    if para_lines:
                        text = "\n".join(para_lines).strip()
                        if text:
                            blocks.append({"type": "段落", "text": text, "page": None, "resource_ref": None})
                        para_lines = []
                    continue
                para_lines.append(line)
            if para_lines:
                text = "\n".join(para_lines).strip()
                if text:
                    blocks.append({"type": "段落", "text": text, "page": None, "resource_ref": None})

    return {
        "file_id": file_id,
        "format": ext,
        "blocks": blocks,
        "resources": [],
    }


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "text-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "text-parser", "parse", _parse,
    description="Parse TXT/MD files into unified content blocks",
    brief="解析文本文件",
    parameters={"file_id": {"type": "int"}},
    min_role="viewer",
)
