"""Core parsing logic for text-parser."""
from __future__ import annotations

MAX_TEXT_BYTES = 1024 * 1024
SUPPORTED_EXTS = {"txt", "md", "markdown", "text", "log"}


class TextParseError(ValueError):
    """Raised when text-parser cannot parse an input file."""


def read_text_sample(path, max_bytes: int = MAX_TEXT_BYTES) -> tuple[bytes, dict[str, int | bool]]:
    file_size = path.stat().st_size
    read_limit = max_bytes + 4 if file_size > max_bytes else max_bytes
    with path.open("rb") as file_obj:
        raw = file_obj.read(read_limit)
    return raw, {
        "original_size": file_size,
        "parsed_bytes": len(raw),
        "max_bytes": max_bytes,
        "truncated": file_size > len(raw),
    }


def decode_text_bytes(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "gb2312"):
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1"), "latin-1"


def _block(block_type: str, text: str) -> dict[str, object]:
    return {"type": block_type, "text": text, "page": None, "resource_ref": None}


def _append_paragraph(blocks: list[dict[str, object]], lines: list[str]) -> None:
    text = "\n".join(lines).strip()
    if text:
        blocks.append(_block("paragraph", text))


def _parse_markdown(lines: list[str]) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_code_block = False

    for line in lines:
        if line.startswith("```"):
            if in_code_block:
                if code_lines:
                    blocks.append(_block("code", "\n".join(code_lines)))
                    code_lines = []
                in_code_block = False
            else:
                _append_paragraph(blocks, paragraph_lines)
                paragraph_lines = []
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if line.startswith("#"):
            _append_paragraph(blocks, paragraph_lines)
            paragraph_lines = []
            title_text = line.lstrip("#").strip()
            if title_text:
                blocks.append(_block("heading", title_text))
            continue

        if line.strip() == "":
            _append_paragraph(blocks, paragraph_lines)
            paragraph_lines = []
            continue

        paragraph_lines.append(line)

    _append_paragraph(blocks, paragraph_lines)
    if code_lines:
        blocks.append(_block("code", "\n".join(code_lines)))
    return blocks


def _parse_plain_text(lines: list[str]) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    paragraph_lines: list[str] = []
    for line in lines:
        if line.strip() == "":
            _append_paragraph(blocks, paragraph_lines)
            paragraph_lines = []
            continue
        paragraph_lines.append(line)
    _append_paragraph(blocks, paragraph_lines)
    return blocks


def parse_text_bytes(file_id: int, raw: bytes, ext: str, metadata: dict[str, object] | None = None) -> dict[str, object]:
    normalized_ext = ext.lower()
    if normalized_ext not in SUPPORTED_EXTS:
        raise TextParseError(f"Unsupported format '{normalized_ext}'")

    content, encoding = decode_text_bytes(raw)
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.splitlines(keepends=False)
    is_markdown = normalized_ext in ("md", "markdown")
    blocks = _parse_markdown(lines) if is_markdown else _parse_plain_text(lines)

    result_metadata = dict(metadata or {})
    result_metadata["encoding"] = encoding

    return {
        "file_id": file_id,
        "format": "markdown" if is_markdown else normalized_ext,
        "blocks": blocks,
        "resources": [],
        "metadata": result_metadata,
    }


def parse_text_file(file_id: int, path, ext: str, max_bytes: int = MAX_TEXT_BYTES) -> dict[str, object]:
    raw, metadata = read_text_sample(path, max_bytes=max_bytes)
    return parse_text_bytes(file_id, raw, ext, metadata=metadata)
