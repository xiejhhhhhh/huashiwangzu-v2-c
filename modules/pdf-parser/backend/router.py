"""FastAPI router for pdf-parser module.

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

router = APIRouter(prefix="/api/pdf-parser", tags=["pdf-parser"])


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
    """Parse PDF file into unified content blocks. Called via cross-module capability."""
    file_id = int(params.get("file_id", 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.config import get_settings
    from app.core.exceptions import NotFound, ValidationError, AppException
    from app.services.file_service import check_file_access
    from pathlib import Path
    import pdfplumber

    allowed = {"pdf"}
    user_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        ext = (file.extension or "").lower()
        if ext not in allowed:
            raise ValidationError(f"Unsupported format '{ext}'. Allowed: {', '.join(sorted(allowed))}")
        if not file.storage_path:
            raise NotFound("File storage path is empty")
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
            raise AppException("Unsafe file storage path", status_code=400)
        if not full_path.exists() or not full_path.is_file():
            raise NotFound("File on disk not found")

        blocks = []
        resources = []
        resource_counter = 0

        with pdfplumber.open(str(full_path)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                pno = page_idx + 1

                text = page.extract_text() or ""
                lines = [l.rstrip() for l in text.splitlines() if l.strip()]
                if lines:
                    block_text = "\n".join(lines).strip()
                    if block_text:
                        block_type = "标题" if pno == 1 and len(lines) <= 5 else "段落"
                        blocks.append({"type": block_type, "text": block_text, "page": pno, "resource_ref": None})

                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue
                    rows = []
                    for row in table:
                        cells = [str(c).strip() if c else "" for c in row]
                        rows.append(" | ".join(cells))
                    table_text = "\n".join(rows)
                    if table_text.strip():
                        blocks.append({"type": "表格", "text": table_text, "page": pno, "resource_ref": None})

                for img in page.images:
                    resource_counter += 1
                    xref = img.get("xref") or img.get("name", "")
                    blocks.append({"type": "图片", "text": "", "page": pno, "resource_ref": resource_counter})
                    resources.append({
                        "id": resource_counter,
                        "type": "图片",
                        "file_storage_id": None,
                        "text_desc": f"PDF page {pno} embedded image (xref={xref})",
                    })

    return {
        "file_id": file_id,
        "format": "pdf",
        "blocks": blocks,
        "resources": resources,
    }


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "pdf-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


# Register capability at import time
register_capability(
    "pdf-parser", "parse", _parse,
    description="Parse PDF files into unified content blocks",
    brief="解析 PDF 文档",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
