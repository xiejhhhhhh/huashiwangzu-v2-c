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
SCHEMA_VERSION = "content-ir/v1"


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


def _source_ref(
    file_id: int,
    line_start: int | None,
    line_end: int | None = None,
    section: str = "body",
) -> dict:
    return {
        "file_id": file_id,
        "format": "markdown",
        "section": section,
        "line_start": line_start,
        "line_end": line_end if line_end is not None else line_start,
    }


def _content_block(
    block_type: str,
    text: str,
    resource_ref: int | None = None,
    source_ref: dict | None = None,
) -> dict:
    return {
        "type": block_type,
        "text": text,
        "page": None,
        "resource_ref": resource_ref,
        "source_ref": source_ref or {},
    }


def parse_markdown_content(content: str, file_id: int) -> dict:
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.splitlines(keepends=False)

    blocks = []
    resources = []
    resource_counter = 0
    in_code_block = False
    code_start: int | None = None
    code_lang = ""
    code_lines: list[str] = []
    para_lines: list[str] = []
    para_start: int | None = None
    in_table = False
    table_lines: list[str] = []
    table_start: int | None = None
    in_list = False
    list_lines: list[str] = []
    list_start: int | None = None

    def flush_para(end_line: int | None = None):
        nonlocal para_lines, para_start
        if para_lines:
            text = "\n".join(para_lines).strip()
            if text:
                blocks.append(_content_block(
                    "paragraph",
                    text,
                    source_ref=_source_ref(file_id, para_start, end_line, "paragraph"),
                ))
            para_lines = []
            para_start = None

    def flush_code(end_line: int | None = None):
        nonlocal code_lines, code_lang, code_start
        if code_lines:
            text = "\n".join(code_lines)
            source_ref = _source_ref(file_id, code_start, end_line, "code")
            if code_lang:
                source_ref["language"] = code_lang
            blocks.append(_content_block("code", text, source_ref=source_ref))
        code_lines = []
        code_lang = ""
        code_start = None

    def flush_table(end_line: int | None = None):
        nonlocal table_lines, table_start
        if table_lines:
            text = "\n".join(table_lines)
            blocks.append(_content_block(
                "table",
                text,
                source_ref=_source_ref(file_id, table_start, end_line, "table"),
            ))
            table_lines = []
            table_start = None

    def flush_list(end_line: int | None = None):
        nonlocal list_lines, list_start
        if list_lines:
            text = "\n".join(list_lines)
            blocks.append(_content_block(
                "list",
                text,
                source_ref=_source_ref(file_id, list_start, end_line, "list"),
            ))
            list_lines = []
            list_start = None

    def append_image(alt_text: str, url: str, line_number: int) -> None:
        nonlocal resource_counter
        resource_counter += 1
        image_source = _source_ref(file_id, line_number, section="image")
        image_source["url"] = url
        blocks.append(_content_block("image", alt_text, resource_counter, image_source))
        resources.append({
            "id": resource_counter,
            "type": "image",
            "file_storage_id": None,
            "text_desc": f"Markdown image: {url} ({alt_text})",
            "source_ref": image_source,
        })

    for line_number, line in enumerate(lines, start=1):
        code_match = CODE_FENCE_RE.match(line)
        if code_match:
            if in_code_block:
                flush_code(line_number)
                in_code_block = False
            else:
                flush_para(line_number - 1)
                flush_table(line_number - 1)
                flush_list(line_number - 1)
                code_lang = code_match.group(1) or ""
                in_code_block = True
                code_start = line_number
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if TABLE_SEP_RE.match(line):
            continue

        if TABLE_ROW_RE.match(line):
            flush_para(line_number - 1)
            flush_list(line_number - 1)
            in_table = True
            if table_start is None:
                table_start = line_number
            table_lines.append(line)
            continue
        if in_table:
            flush_table(line_number - 1)
            in_table = False

        m = HEADING_RE.match(line)
        if m:
            flush_para(line_number - 1)
            flush_list(line_number - 1)
            level = len(m.group(1))
            title_text = m.group(2).strip()
            block_type = "heading" if level <= 2 else "paragraph"
            source_ref = _source_ref(file_id, line_number, section="heading")
            source_ref["level"] = level
            blocks.append(_content_block(block_type, title_text, source_ref=source_ref))
            continue

        if BLOCKQUOTE_RE.match(line):
            flush_para(line_number - 1)
            flush_list(line_number - 1)
            m = BLOCKQUOTE_RE.match(line)
            quote_text = m.group(1).strip()
            if quote_text:
                blocks.append(_content_block(
                    "quote",
                    quote_text,
                    source_ref=_source_ref(file_id, line_number, section="quote"),
                ))
            continue

        if HORIZONTAL_RULE_RE.match(line):
            flush_para(line_number - 1)
            flush_list(line_number - 1)
            blocks.append(_content_block(
                "divider",
                "",
                source_ref=_source_ref(file_id, line_number, section="divider"),
            ))
            continue

        image_match = IMAGE_RE.fullmatch(line.strip())
        if image_match:
            flush_para(line_number - 1)
            flush_table(line_number - 1)
            flush_list(line_number - 1)
            append_image(image_match.group(1) or "", image_match.group(2) or "", line_number)
            continue

        if LIST_ITEM_RE.match(line) or ORDERED_LIST_RE.match(line):
            flush_para(line_number - 1)
            in_list = True
            if list_start is None:
                list_start = line_number
            list_lines.append(line)
            continue
        if in_list:
            if line.strip() == "":
                flush_list(line_number - 1)
                in_list = False
                continue
            if LIST_ITEM_RE.match(line) or ORDERED_LIST_RE.match(line):
                list_lines.append(line)
                continue
            list_lines.append(line)
            continue

        if line.strip() == "":
            flush_para(line_number - 1)
            continue

        if para_start is None:
            para_start = line_number
        para_lines.append(line)

    flush_para(len(lines))
    flush_code(len(lines))
    flush_table(len(lines))
    flush_list(len(lines))
    if not blocks:
        blocks.append(_content_block(
            "paragraph",
            "(empty markdown file)",
            source_ref={**_source_ref(file_id, None, None, "body"), "empty": True},
        ))

    return {
        "schema_version": SCHEMA_VERSION,
        "content_type": "mixed",
        "title": "Markdown document",
        "source_file_id": file_id,
        "source_module": "markdown-parser",
        "parser": "markdown-parser",
        "source": {
            "module": "markdown-parser",
            "file_id": file_id,
            "filename": None,
            "mime_type": None,
            "format": "markdown",
        },
        "file_id": file_id,
        "format": "markdown",
        "blocks": blocks,
        "resources": resources,
        "metadata": {},
        "warnings": [],
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
