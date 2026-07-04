"""Core parsing logic for text-parser."""
from __future__ import annotations

MAX_TEXT_BYTES = 1024 * 1024
SUPPORTED_EXTS = {"txt", "md", "markdown", "text", "log"}
SCHEMA_VERSION = "content-ir/v1"


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


def _source_ref(
    file_id: int,
    file_format: str,
    line_start: int | None,
    line_end: int | None = None,
    section: str = "body",
) -> dict[str, object]:
    return {
        "file_id": file_id,
        "format": file_format,
        "section": section,
        "line_start": line_start,
        "line_end": line_end if line_end is not None else line_start,
    }


def _block(
    block_type: str,
    text: str,
    source_ref: dict[str, object],
) -> dict[str, object]:
    return {
        "type": block_type,
        "text": text,
        "page": None,
        "resource_ref": None,
        "source_ref": source_ref,
    }


def _append_paragraph(
    blocks: list[dict[str, object]],
    lines: list[str],
    source_ref: dict[str, object] | None,
) -> None:
    text = "\n".join(lines).strip()
    if text and source_ref:
        blocks.append(_block("paragraph", text, source_ref))


def _parse_markdown(lines: list[str], file_id: int, file_format: str) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    paragraph_lines: list[str] = []
    paragraph_start: int | None = None
    code_lines: list[str] = []
    code_start: int | None = None
    in_code_block = False

    for line_number, line in enumerate(lines, start=1):
        if line.startswith("```"):
            if in_code_block:
                if code_lines:
                    blocks.append(_block(
                        "code",
                        "\n".join(code_lines),
                        _source_ref(file_id, file_format, code_start, line_number, "code"),
                    ))
                    code_lines = []
                in_code_block = False
                code_start = None
            else:
                _append_paragraph(
                    blocks,
                    paragraph_lines,
                    _source_ref(file_id, file_format, paragraph_start, line_number - 1),
                )
                paragraph_lines = []
                paragraph_start = None
                in_code_block = True
                code_start = line_number
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if line.startswith("#"):
            _append_paragraph(
                blocks,
                paragraph_lines,
                _source_ref(file_id, file_format, paragraph_start, line_number - 1),
            )
            paragraph_lines = []
            paragraph_start = None
            title_text = line.lstrip("#").strip()
            if title_text:
                blocks.append(_block(
                    "heading",
                    title_text,
                    _source_ref(file_id, file_format, line_number, section="heading"),
                ))
            continue

        if line.strip() == "":
            _append_paragraph(
                blocks,
                paragraph_lines,
                _source_ref(file_id, file_format, paragraph_start, line_number - 1),
            )
            paragraph_lines = []
            paragraph_start = None
            continue

        if paragraph_start is None:
            paragraph_start = line_number
        paragraph_lines.append(line)

    _append_paragraph(
        blocks,
        paragraph_lines,
        _source_ref(file_id, file_format, paragraph_start, len(lines)),
    )
    if code_lines:
        blocks.append(_block(
            "code",
            "\n".join(code_lines),
            _source_ref(file_id, file_format, code_start, len(lines), "code"),
        ))
    return blocks


def _parse_plain_text(lines: list[str], file_id: int, file_format: str) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    paragraph_lines: list[str] = []
    paragraph_start: int | None = None
    for line_number, line in enumerate(lines, start=1):
        if line.strip() == "":
            _append_paragraph(
                blocks,
                paragraph_lines,
                _source_ref(file_id, file_format, paragraph_start, line_number - 1),
            )
            paragraph_lines = []
            paragraph_start = None
            continue
        if paragraph_start is None:
            paragraph_start = line_number
        paragraph_lines.append(line)
    _append_paragraph(
        blocks,
        paragraph_lines,
        _source_ref(file_id, file_format, paragraph_start, len(lines)),
    )
    return blocks


def parse_text_bytes(file_id: int, raw: bytes, ext: str, metadata: dict[str, object] | None = None) -> dict[str, object]:
    normalized_ext = ext.lower()
    if normalized_ext not in SUPPORTED_EXTS:
        raise TextParseError(f"Unsupported format '{normalized_ext}'")

    content, encoding = decode_text_bytes(raw)
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.splitlines(keepends=False)
    is_markdown = normalized_ext in ("md", "markdown")
    output_format = "markdown" if is_markdown else normalized_ext
    blocks = (
        _parse_markdown(lines, file_id, output_format)
        if is_markdown else _parse_plain_text(lines, file_id, output_format)
    )
    if not blocks:
        blocks.append(_block(
            "paragraph",
            "(empty text file)",
            {
                **_source_ref(file_id, output_format, None, None, "body"),
                "empty": True,
            },
        ))

    result_metadata = dict(metadata or {})
    result_metadata["encoding"] = encoding

    return {
        "schema_version": SCHEMA_VERSION,
        "content_type": "text",
        "title": f"{output_format} text",
        "source_file_id": file_id,
        "source_module": "text-parser",
        "parser": "text-parser",
        "source": {
            "module": "text-parser",
            "file_id": file_id,
            "filename": None,
            "mime_type": None,
            "format": output_format,
        },
        "file_id": file_id,
        "format": output_format,
        "blocks": blocks,
        "resources": [],
        "metadata": result_metadata,
        "warnings": [],
    }


def parse_text_file(file_id: int, path, ext: str, max_bytes: int = MAX_TEXT_BYTES) -> dict[str, object]:
    raw, metadata = read_text_sample(path, max_bytes=max_bytes)
    return parse_text_bytes(file_id, raw, ext, metadata=metadata)
