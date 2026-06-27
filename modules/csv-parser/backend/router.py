"""FastAPI router for csv-parser module.

Parses CSV and TSV files into unified content blocks.
Each row becomes a structured text block; column headers are preserved.
"""
import csv
import io
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability

router = APIRouter(prefix="/api/csv-parser", tags=["csv-parser"])


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


def _detect_delimiter(head: str) -> str:
    if "\t" in head:
        return "\t"
    if ";" in head:
        return ";"
    return ","


async def _parse(params: dict, caller: str) -> dict:
    file_id = int(params.get("file_id", 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.config import get_settings
    from app.core.exceptions import NotFound, ValidationError, AppException
    from app.services.file_service import check_file_access
    from pathlib import Path

    allowed = {"csv", "tsv"}
    user_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        ext = (file.extension or "").lower()
        if ext not in allowed:
            raise ValidationError(f"Unsupported format '{ext}'. Allowed: csv, tsv")
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
        lines = content.strip().splitlines()
        if not lines:
            return {"file_id": file_id, "format": ext, "blocks": [], "resources": []}

        delimiter = _detect_delimiter(lines[0])
        reader = csv.reader(lines, delimiter=delimiter)

        rows = list(reader)
        if not rows:
            return {"file_id": file_id, "format": ext, "blocks": [], "resources": []}

        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

        # Summary block
        summary = f"表格：{len(headers)}列 x {len(data_rows)}行数据"
        if headers:
            summary += f"\n表头：{' | '.join(headers)}"
        blocks.append({"type": "段落", "text": summary, "page": None, "resource_ref": None})

        # Header block
        if headers:
            blocks.append({"type": "表格", "text": " | ".join(headers), "page": None, "resource_ref": None})

        # Data blocks - batch in groups of 50 rows
        batch_size = 50
        for start in range(0, len(data_rows), batch_size):
            batch = data_rows[start:start + batch_size]
            row_texts = []
            for i, row in enumerate(batch):
                line_num = start + i + 2
                cols = " | ".join(row)
                row_texts.append(f"行{line_num}：{cols}")
            block_text = "\n".join(row_texts)
            blocks.append({"type": "表格", "text": block_text, "page": None, "resource_ref": None})

    return {
        "file_id": file_id,
        "format": ext,
        "blocks": blocks,
        "resources": [],
    }


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "csv-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "csv-parser", "parse", _parse,
    description="Parse CSV/TSV files into unified content blocks",
    brief="解析 CSV/TSV 表格文件",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
