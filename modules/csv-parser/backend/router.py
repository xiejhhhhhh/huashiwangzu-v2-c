import csv
import io
from pathlib import Path

from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.file_reader import decode_text_bytes
from app.services.module_registry import register_capability
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/api/csv-parser", tags=["csv-parser"])

MAX_EMITTED_DATA_ROWS = 1000
DATA_BLOCK_BATCH_SIZE = 50
MAX_CELL_CHARS = 500
SNIFFER_SAMPLE_CHARS = 8192


class ParseRequest(BaseModel):
    file_id: int


def _coerce_file_id(params: dict) -> int:
    try:
        file_id = int(params.get("file_id", 0))
    except (TypeError, ValueError):
        raise ValidationError("file_id must be a positive integer")
    if file_id <= 0:
        raise ValidationError("file_id must be a positive integer")
    return file_id


def _delimiter_label(delimiter: str) -> str:
    if delimiter == "\t":
        return "tab"
    if delimiter == ";":
        return "semicolon"
    if delimiter == "|":
        return "pipe"
    return ","


def _detect_delimiter(sample: str, ext: str) -> str:
    if ext == "tsv":
        return "\t"

    candidate_lines = [line for line in sample.splitlines() if line.strip()]
    if not candidate_lines:
        return ","
    probe = "\n".join(candidate_lines[:20])
    try:
        dialect = csv.Sniffer().sniff(probe, delimiters=",\t;|")
        if dialect.delimiter in {",", "\t", ";", "|"}:
            return dialect.delimiter
    except csv.Error:
        pass

    counts = {
        delimiter: sum(line.count(delimiter) for line in candidate_lines[:20])
        for delimiter in (",", "\t", ";", "|")
    }
    delimiter, count = max(counts.items(), key=lambda item: item[1])
    return delimiter if count > 0 else ","


def _block(block_type: str, text: str) -> dict[str, object]:
    return {"type": block_type, "text": text, "page": None, "resource_ref": None}


def _trim_cell(cell: str) -> str:
    normalized = cell.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(normalized) <= MAX_CELL_CHARS:
        return normalized
    return f"{normalized[:MAX_CELL_CHARS]}..."


def _format_row(line_num: int, row: list[str]) -> str:
    return f"行{line_num}：" + " | ".join(_trim_cell(cell) for cell in row)


def parse_csv_content(content: str, file_id: int, ext: str) -> dict[str, object]:
    content = content.lstrip("\ufeff")
    if not content.strip():
        return {
            "file_id": file_id,
            "format": ext,
            "blocks": [_block("段落", "空CSV/TSV文件：0列 x 0行数据")],
            "resources": [],
        }

    delimiter = _detect_delimiter(content[:SNIFFER_SAMPLE_CHARS], ext)
    reader = csv.reader(io.StringIO(content), delimiter=delimiter, strict=True)

    headers: list[str] = []
    data_row_count = 0
    emitted_row_count = 0
    row_texts: list[str] = []
    data_blocks: list[dict[str, object]] = []

    try:
        for physical_line, row in enumerate(reader, start=1):
            if physical_line == 1:
                headers = row
                continue

            data_row_count += 1
            if emitted_row_count >= MAX_EMITTED_DATA_ROWS:
                continue

            emitted_row_count += 1
            row_texts.append(_format_row(physical_line, row))
            if len(row_texts) >= DATA_BLOCK_BATCH_SIZE:
                data_blocks.append(_block("表格", "\n".join(row_texts)))
                row_texts = []
    except csv.Error as exc:
        raise ValidationError(f"Invalid CSV content: {exc}")

    if row_texts:
        data_blocks.append(_block("表格", "\n".join(row_texts)))

    summary = f"表格：{len(headers)}列 x {data_row_count}行数据"
    summary += f"\n分隔符：{_delimiter_label(delimiter)}"
    if headers:
        summary += f"\n表头：{' | '.join(_trim_cell(header) for header in headers)}"
    if data_row_count > emitted_row_count:
        omitted = data_row_count - emitted_row_count
        summary += f"\n仅输出前 {emitted_row_count} 行，剩余 {omitted} 行已省略。"

    blocks = [_block("段落", summary)]
    if headers:
        blocks.append(_block("表格", " | ".join(_trim_cell(header) for header in headers)))
    blocks.extend(data_blocks)

    return {
        "file_id": file_id,
        "format": ext,
        "blocks": blocks,
        "resources": [],
    }


def parse_csv_path(file_id: int, full_path: Path, ext: str) -> dict[str, object]:
    content = decode_text_bytes(full_path.read_bytes())
    return parse_csv_content(content, file_id, ext)


async def _parse(params: dict, caller: str) -> dict:
    allowed = {"csv", "tsv"}
    file_id = _coerce_file_id(params)

    def parse_file(file_id: int, _file: object, full_path: Path, ext: str) -> dict[str, object]:
        return parse_csv_path(file_id, full_path, ext)

    return await run_uploaded_file_capability({"file_id": file_id}, caller, allowed, parse_file)


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
