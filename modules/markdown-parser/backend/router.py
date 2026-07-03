import re

from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.file_reader import decode_text_bytes
from app.services.module_registry import register_capability
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/markdown-parser", tags=["markdown-parser"])


class ParseRequest(BaseModel):
    file_id: int = Field(gt=0)


def _require_file_id(params: dict) -> int:
    raw_file_id = params.get("file_id")
    if isinstance(raw_file_id, bool):
        raise ValidationError("file_id must be a positive integer")
    try:
        file_id = int(raw_file_id)
    except (TypeError, ValueError):
        raise ValidationError("file_id must be a positive integer") from None
    if file_id <= 0:
        raise ValidationError("file_id must be a positive integer")
    return file_id


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
CODE_FENCE_RE = re.compile(r"^`{3,}\s*(\w*)$")
TABLE_ROW_RE = re.compile(r"^\|.+\|$")
TABLE_SEP_RE = re.compile(r"^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|$")
LIST_ITEM_RE = re.compile(r"^(\s*)[-*+]\s+")
ORDERED_LIST_RE = re.compile(r"^(\s*)\d+[.)]\s+")
BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
HORIZONTAL_RULE_RE = re.compile(r"^[-*_]{3,}\s*$")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _content_block(block_type: str, text: str, resource_ref: int | None = None) -> dict:
    return {"type": block_type, "text": text, "page": None, "resource_ref": resource_ref}


def parse_markdown_content(content: str, file_id: int) -> dict:
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
                blocks.append(_content_block("paragraph", text))
            para_lines = []

    def flush_code():
        nonlocal code_lines, code_lang
        if code_lines:
            text = "\n".join(code_lines)
            blocks.append(_content_block("code", text))
        code_lines = []
        code_lang = ""

    def flush_table():
        nonlocal table_lines
        if table_lines:
            text = "\n".join(table_lines)
            blocks.append(_content_block("table", text))
            table_lines = []

    def flush_list():
        nonlocal list_lines
        if list_lines:
            text = "\n".join(list_lines)
            blocks.append(_content_block("list", text))
            list_lines = []

    def append_image(alt_text: str, url: str) -> None:
        nonlocal resource_counter
        resource_counter += 1
        blocks.append(_content_block("image", alt_text, resource_counter))
        resources.append({
            "id": resource_counter,
            "type": "image",
            "file_storage_id": None,
            "text_desc": f"Markdown image: {url} ({alt_text})",
        })

    for line in lines:
        code_match = CODE_FENCE_RE.match(line)
        if code_match:
            if in_code_block:
                flush_code()
                in_code_block = False
            else:
                flush_para()
                flush_table()
                flush_list()
                code_lang = code_match.group(1) or ""
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if TABLE_SEP_RE.match(line):
            continue

        if TABLE_ROW_RE.match(line):
            flush_para()
            flush_list()
            in_table = True
            table_lines.append(line)
            continue
        if in_table:
            flush_table()
            in_table = False

        m = HEADING_RE.match(line)
        if m:
            flush_para()
            flush_list()
            level = len(m.group(1))
            title_text = m.group(2).strip()
            block_type = "heading" if level <= 2 else "paragraph"
            blocks.append(_content_block(block_type, title_text))
            continue

        if BLOCKQUOTE_RE.match(line):
            flush_para()
            flush_list()
            m = BLOCKQUOTE_RE.match(line)
            quote_text = m.group(1).strip()
            if quote_text:
                blocks.append(_content_block("paragraph", f">{quote_text}"))
            continue

        if HORIZONTAL_RULE_RE.match(line):
            flush_para()
            flush_list()
            continue

        image_match = IMAGE_RE.fullmatch(line.strip())
        if image_match:
            flush_para()
            flush_table()
            flush_list()
            append_image(image_match.group(1) or "", image_match.group(2) or "")
            continue

        if LIST_ITEM_RE.match(line) or ORDERED_LIST_RE.match(line):
            flush_para()
            in_list = True
            list_lines.append(line)
            continue
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

    return {
        "file_id": file_id,
        "format": "markdown",
        "blocks": blocks,
        "resources": resources,
    }


async def _parse(params: dict, caller: str) -> dict:
    allowed = {"md", "markdown"}
    file_id = _require_file_id(params)

    def parse_file(valid_file_id, _file, full_path, _ext):
        content = decode_text_bytes(full_path.read_bytes())
        return parse_markdown_content(content, valid_file_id)

    return await run_uploaded_file_capability({"file_id": file_id}, caller, allowed, parse_file)


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
