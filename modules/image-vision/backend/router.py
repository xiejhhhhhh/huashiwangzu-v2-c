"""FastAPI router for image-vision module.

Registers the describe capability with the framework's cross-module registry.
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

router = APIRouter(prefix="/api/image-vision", tags=["image-vision"])


class DescribeRequest(BaseModel):
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


async def _describe(params: dict, caller: str) -> dict:
    """Generate text description of an image via vision model."""
    file_id = int(params.get("file_id", 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.config import get_settings
    from app.core.exceptions import NotFound, ValidationError, AppException
    from app.services.file_service import check_file_access
    from pathlib import Path
    import base64
    import io

    allowed = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "ico"}
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

        raw = full_path.read_bytes()
        fmt_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif",
                   "webp": "webp", "bmp": "bmp", "ico": "png"}
        mime_fmt = fmt_map.get(ext, "jpeg")

        # Try gateway vision model; fallback to metadata only
        try:
            from app.services.model_services import describe_image
            description = await describe_image(
                raw,
                prompt="请详细描述这张图片中的内容，包括文字、物体、布局等。",
                mime_type=f"image/{mime_fmt}",
            )
        except Exception as exc:
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(raw))
                dims = f"{img.width}x{img.height}"
                description = f"[Image metadata] {file.name}.{file.extension}, {dims}px, mode={img.mode}. Vision unavailable: {exc}"
            except Exception:
                description = f"[Image metadata] {file.name}.{file.extension}, {len(raw)} bytes. Vision unavailable."

        blocks = [
            {"type": "图片", "text": description, "page": None, "resource_ref": 1},
        ]
        resources = [
            {"id": 1, "type": "图片", "file_storage_id": file_id, "text_desc": description},
        ]

    return {
        "file_id": file_id,
        "format": ext,
        "blocks": blocks,
        "resources": resources,
    }


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "image-vision", "status": "ok"})


@router.post("/describe")
async def call_describe(payload: DescribeRequest, user: User = Depends(require_permission("viewer"))):
    result = await _describe({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "image-vision", "describe", _describe,
    description="Generate text description of images via vision model",
    brief="识别图片内容",
    parameters={"file_id": {"type": "int"}},
    min_role="viewer",
)
