"""FastAPI router for markdown-parser module.

Properly parses Markdown into the unified Document IR with heading levels,
code blocks, tables, lists, and embedded resource references.
"""
import os
import re
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability

router = APIRouter(prefix="/api/markdown-parser", tags=["markdown-parser"])


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


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
CODE_FENCE_RE = re.compile(r"^`{3,}\s*(\w*)$")
TABLE_ROW_RE = re.compile(r"^\|.+\|$")
TABLE_SEP_RE = re.compile(r"^\|[\s:-]+\|$")
LIST_ITEM_RE = re.compile(r"^(\s*)[-*+]\s+")
ORDERED_LIST_RE = re.compile(r"^(\s*)\d+[.)]\s+")
BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
HORIZONTAL_RULE_RE = re.compile(r"^[-*_]{3,}\s*$")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


async def _parse(params: dict, caller: str) -> dict:
    file_id = int(params.get("file_id", 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.config import get_settings
    from app.core.exceptions import NotFound, ValidationError, AppException
    from app.services.file_service import check_file_access
    from pathlib import Path

    allowed = {"md", "markdown"}
    user_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        ext = (file.extension or "").lower()
        if ext not in allowed:
            raise ValidationError(f"Unsupported format '{ext}'. Allowed: md, markdown")
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
        resources = []
        resource_counter = 0
        in_code_block = False
        code_lang = ""
        code_lines: list[str] = []
        para_lines: list[str] = []
        in_table = False
        table_lines: list[str] = []
        in_list = False
        list_lines: list[str] = []

        def flush_para():
            nonlocal para_lines
            if para_lines:
                text = "\n".join(para_lines).strip()
                if text:
                    blocks.append({"type": "段落", "text": text, "page": None, "resource_ref": None})
                para_lines = []

        def flush_code():
            nonlocal code_lines, code_lang
            if code_lines:
                text = "\n".join(code_lines)
                blocks.append({"type": "代码", "text": text, "page": None, "resource_ref": None})
                code_lines = []
                code_lang = ""

        def flush_table():
            nonlocal table_lines
            if table_lines:
                text = "\n".join(table_lines)
                blocks.append({"type": "表格", "text": text, "page": None, "resource_ref": None})
                table_lines = []

        def flush_list():
            nonlocal list_lines
            if list_lines:
                text = "\n".join(list_lines)
                blocks.append({"type": "段落", "text": text, "page": None, "resource_ref": None})
                list_lines = []

        for line in lines:
            if not in_code_block and CODE_FENCE_RE.match(line):
                flush_para()
                flush_table()
                flush_list()
                if in_code_block:
                    flush_code()
                    in_code_block = False
                else:
                    m = CODE_FENCE_RE.match(line)
                    code_lang = m.group(1) or ""
                    in_code_block = True
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            if not in_code_block and TABLE_SEP_RE.match(line):
                continue

            if not in_code_block and TABLE_ROW_RE.match(line):
                flush_para()
                flush_list()
                in_table = True
                table_lines.append(line)
                continue
            else:
                if in_table:
                    flush_table()
                    in_table = False

            m = HEADING_RE.match(line)
            if m:
                flush_para()
                flush_list()
                level = len(m.group(1))
                title_text = m.group(2).strip()
                bt = "标题" if level <= 2 else "段落"
                blocks.append({"type": bt, "text": title_text, "page": None, "resource_ref": None})
                continue

            if not in_code_block and BLOCKQUOTE_RE.match(line):
                flush_para()
                flush_list()
                m = BLOCKQUOTE_RE.match(line)
                quote_text = m.group(1).strip()
                if quote_text:
                    blocks.append({"type": "段落", "text": f">{quote_text}", "page": None, "resource_ref": None})
                continue

            if not in_code_block and HORIZONTAL_RULE_RE.match(line):
                flush_para()
                flush_list()
                continue

            if LIST_ITEM_RE.match(line) or ORDERED_LIST_RE.match(line):
                flush_para()
                in_list = True
                list_lines.append(line)
                continue
            else:
                if in_list:
                    if line.strip() == "":
                        flush_list()
                        in_list = False
                        continue
                    if LIST_ITEM_RE.match(line) or ORDERED_LIST_RE.match(line):
                        list_lines.append(line)
                        continue
                    list_lines.append(line)
                    continue

            if line.strip() == "":
                flush_para()
                continue

            para_lines.append(line)

        flush_para()
        flush_code()
        flush_table()
        flush_list()

        for img_match in IMAGE_RE.finditer(content):
            resource_counter += 1
            alt_text = img_match.group(1) or ""
            url = img_match.group(2) or ""
            blocks.append({"type": "图片", "text": alt_text, "page": None, "resource_ref": resource_counter})
            resources.append({
                "id": resource_counter,
                "type": "图片",
                "file_storage_id": None,
                "text_desc": f"Markdown image: {url} ({alt_text})",
            })

    return {
        "file_id": file_id,
        "format": "markdown",
        "blocks": blocks,
        "resources": resources,
    }


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "markdown-parser", "status": "ok"})


@router.post("/parse")
async def call_parse(payload: ParseRequest, user: User = Depends(require_permission("viewer"))):
    result = await _parse({"file_id": payload.file_id}, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "markdown-parser", "parse", _parse,
    description="Parse Markdown files into unified content blocks with heading levels",
    brief="解析 Markdown 文档",
    parameters={"file_id": {"type": "int", "description": "File ID in file storage"}},
    min_role="viewer",
)
