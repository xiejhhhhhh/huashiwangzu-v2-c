"""FastAPI router for structured-parser module.

Parses JSON and YAML files into unified content blocks.
Flattens nested structures into readable text blocks.
"""
import json
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability

router = APIRouter(prefix="/api/structured-parser", tags=["structured-parser"])


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


def _flatten_json(obj: object, prefix: str = "", depth: int = 0, max_depth: int = 10) -> list[str]:
    if depth > max_depth:
        return [f"{prefix}: (max depth reached)"]
    lines: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                lines.extend(_flatten_json(v, path, depth + 1, max_depth))
            else:
                lines.append(f"{path}: {v}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            path = f"{prefix}[{i}]"
            if isinstance(item, (dict, list)):
                lines.extend(_flatten_json(item, path, depth + 1, max_depth))
            else:
                lines.append(f"{path}: {item}")
    else:
        lines.append(f"{prefix}: {obj}")
    return lines


async def _parse(params: dict, caller: str) -> dict:
    file_id = int(params.get("file_id", 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.config import get_settings
    from app.core.exceptions import NotFound, ValidationError, AppException
    from app.services.file_service import check_file_access
    from pathlib import Path

    allowed = {"json", "yaml", "yml"}
    user_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        ext = (file.extension or "").lower()
        if ext not in allowed:
            raise ValidationError(f"Unsupported format '{ext}'. Allowed: json, yaml, yml")
        if not file.storage_path:
            raise NotFound("File storage path is empty")
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
            raise AppException("Unsafe file storage path", status_code=400)
        if not full_path.exists() or not full_path.is_file():
            raise NotFound("File on disk not found")

        raw = full_path.read_bytes()
        ALLOWED_ENCS = ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"]
        content = None
        for enc in ALLOWED_ENCS:
            try:
                content = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if content is None:
            content = raw.decode("utf-8", errors="replace")

        blocks = []
        content = content.strip()
        if not content:
            return {"file_id": file_id, "format": ext, "blocks": [], "resources": []}

        data: object = None
        if ext in ("yaml", "yml"):
            try:
                import yaml
                data = yaml.safe_load(content)
            except ImportError:
                raise ValidationError("YAML parsing requires PyYAML library")
            except Exception as e:
                raise ValidationError(f"Invalid YAML: {e}")
        else:
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise ValidationError(f"Invalid JSON: {e}")

        lines = _flatten_json(data)
        if lines:
            summary = f"结构化数据：{len(lines)} 个字段"
            blocks.append({"type": "段落", "text": summary, "page": None, "resource_ref": None})

            batch_size = 30
            for start in range(0, len(lines), batch_size):
                batch = lines[start:start + batch_size]
                blocks.append({
                    "type": "段落",
                    "text": "\n".join(batch),
                    "page": None,
                    "resource_ref": None,
                })

    return {
        "file_id": file_id,
        "format": ext,
        "blocks": blocks,
        "resources": [],
    }


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "structured-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "structured-parser", "parse", _parse,
    description="Parse JSON/YAML files into unified content blocks",
    brief="解析 JSON/YAML 结构化文件",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
