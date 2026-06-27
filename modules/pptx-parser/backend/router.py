"""FastAPI router for pptx-parser module.

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

router = APIRouter(prefix="/api/pptx-parser", tags=["pptx-parser"])


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
    """Parse PPTX file into unified content blocks."""
    file_id = int(params.get("file_id", 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.config import get_settings
    from app.core.exceptions import NotFound, ValidationError, AppException
    from app.services.file_service import check_file_access
    from pathlib import Path
    from pptx import Presentation

    allowed = {"pptx"}
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

        prs = Presentation(str(full_path))
        blocks = []
        resources = []
        resource_counter = 0

        for slide_idx, slide in enumerate(prs.slides):
            pno = slide_idx + 1
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if not text:
                            continue
                        block_type = "标题" if ("title" in str(shape.name).lower() or "标题" in str(shape.name)) else "段落"
                        blocks.append({"type": block_type, "text": text, "page": pno, "resource_ref": None})
                if shape.shape_type and "picture" in str(shape.shape_type).lower():
                    resource_counter += 1
                    blocks.append({"type": "图片", "text": "", "page": pno, "resource_ref": resource_counter})
                    resources.append({
                        "id": resource_counter,
                        "type": "图片",
                        "file_storage_id": None,
                        "text_desc": f"Slide {pno} image ({shape.name})",
                    })

    return {
        "file_id": file_id,
        "format": "pptx",
        "blocks": blocks,
        "resources": resources,
    }


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "pptx-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "pptx-parser", "parse", _parse,
    description="Parse PPTX files into unified content blocks",
    brief="解析 PPTX 文档",
    parameters={"file_id": {"type": "int"}},
    min_role="viewer",
)
