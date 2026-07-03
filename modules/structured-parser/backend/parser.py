"""Core parsing logic for structured-parser."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.services.file_reader import decode_text_bytes

SUPPORTED_EXTS: Final[set[str]] = {"json", "yaml", "yml"}
MAX_STRUCTURED_BYTES: Final[int] = 2 * 1024 * 1024
MAX_EMITTED_FIELDS: Final[int] = 3000
DATA_BLOCK_BATCH_SIZE: Final[int] = 30
MAX_FLATTEN_DEPTH: Final[int] = 10


class StructuredParseError(ValueError):
    """Raised when structured-parser cannot parse an input file."""


class StructuredFileTooLargeError(StructuredParseError):
    """Raised when a structured file exceeds the parser size limit."""


@dataclass(frozen=True)
class FlattenedData:
    lines: list[str]
    total_fields: int
    truncated: bool


def _block(block_type: str, text: str) -> dict[str, object]:
    return {"type": block_type, "text": text, "page": None, "resource_ref": None}


def _format_scalar(value: object) -> str:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def flatten_structured_data(
    obj: object,
    max_depth: int = MAX_FLATTEN_DEPTH,
    max_lines: int = MAX_EMITTED_FIELDS,
) -> FlattenedData:
    lines: list[str] = []
    total_fields = 0
    truncated = False

    def add_line(line: str) -> None:
        nonlocal total_fields, truncated
        total_fields += 1
        if len(lines) < max_lines:
            lines.append(line)
        else:
            truncated = True

    def walk(value: object, path: str, depth: int) -> None:
        if depth > max_depth:
            add_line(f"{path or '$'}: (max depth reached)")
            return

        if isinstance(value, dict):
            for key, item in value.items():
                key_path = str(key)
                child_path = f"{path}.{key_path}" if path else key_path
                if isinstance(item, (dict, list)):
                    walk(item, child_path, depth + 1)
                else:
                    add_line(f"{child_path}: {_format_scalar(item)}")
            return

        if isinstance(value, list):
            for index, item in enumerate(value):
                child_path = f"{path}[{index}]" if path else f"[{index}]"
                if isinstance(item, (dict, list)):
                    walk(item, child_path, depth + 1)
                else:
                    add_line(f"{child_path}: {_format_scalar(item)}")
            return

        add_line(f"{path or '$'}: {_format_scalar(value)}")

    walk(obj, "", 0)
    return FlattenedData(lines=lines, total_fields=total_fields, truncated=truncated)


def _load_structured_content(content: str, ext: str) -> object:
    if ext == "json":
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise StructuredParseError(f"Invalid JSON: {exc}") from exc

    try:
        import yaml
    except ImportError as exc:
        raise StructuredParseError("YAML parsing requires PyYAML library") from exc

    try:
        return yaml.safe_load(content)
    except Exception as exc:
        raise StructuredParseError(f"Invalid YAML: {exc}") from exc


def _build_result(
    file_id: int,
    ext: str,
    flattened: FlattenedData,
    empty_file: bool = False,
) -> dict[str, object]:
    if empty_file:
        summary = "空结构化文件：0 个字段"
    else:
        summary = f"结构化数据：{flattened.total_fields} 个字段"
    if flattened.truncated:
        omitted = flattened.total_fields - len(flattened.lines)
        summary += f"\n仅输出前 {len(flattened.lines)} 个字段，剩余 {omitted} 个字段已省略。"

    blocks = [_block("paragraph", summary)]
    for start in range(0, len(flattened.lines), DATA_BLOCK_BATCH_SIZE):
        batch = flattened.lines[start:start + DATA_BLOCK_BATCH_SIZE]
        blocks.append(_block("paragraph", "\n".join(batch)))

    return {
        "file_id": file_id,
        "format": "yaml" if ext == "yml" else ext,
        "blocks": blocks,
        "resources": [],
        "metadata": {
            "field_count": flattened.total_fields,
            "emitted_fields": len(flattened.lines),
            "truncated": flattened.truncated,
            "max_depth": MAX_FLATTEN_DEPTH,
            "max_emitted_fields": MAX_EMITTED_FIELDS,
            "empty_file": empty_file,
        },
    }


def parse_structured_content(content: str, file_id: int, ext: str) -> dict[str, object]:
    normalized_ext = ext.lower()
    if normalized_ext not in SUPPORTED_EXTS:
        raise StructuredParseError(f"Unsupported format '{normalized_ext}'")

    stripped = content.strip()
    if not stripped:
        return _build_result(
            file_id,
            normalized_ext,
            FlattenedData(lines=[], total_fields=0, truncated=False),
            empty_file=True,
        )

    data = _load_structured_content(stripped, normalized_ext)
    flattened = flatten_structured_data(data)
    return _build_result(file_id, normalized_ext, flattened)


def parse_structured_file(
    file_id: int,
    path: Path,
    ext: str,
    max_bytes: int = MAX_STRUCTURED_BYTES,
) -> dict[str, object]:
    file_size = path.stat().st_size
    if file_size > max_bytes:
        raise StructuredFileTooLargeError(
            f"Structured file is too large: {file_size} bytes exceeds {max_bytes} bytes"
        )
    content = decode_text_bytes(path.read_bytes())
    return parse_structured_content(content, file_id, ext)
