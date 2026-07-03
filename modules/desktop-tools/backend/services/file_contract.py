"""File contract helpers for desktop-tools capabilities."""
from copy import deepcopy

from app.core.exceptions import ValidationError

FILE_FIELDS = (
    "id",
    "name",
    "extension",
    "size",
    "mime_type",
    "folder_id",
    "created_at",
    "updated_at",
)

MAX_PAGE_SIZE = 100
MAX_READ_CHARS = 20_000
MAX_READ_BLOCKS = 80

EXT_PARSER_MAP = {
    "pdf": "pdf-parser",
    "docx": "docx-parser",
    "xlsx": "xlsx-parser",
    "xls": "xlsx-parser",
    "csv": "xlsx-parser",
    "pptx": "pptx-parser",
    "txt": "text-parser",
    "md": "text-parser",
    "markdown": "text-parser",
    "text": "text-parser",
    "log": "text-parser",
}

TEXT_EXTS = {"txt", "md", "markdown", "text", "log", "csv", "json", "xml", "yaml", "yml"}


def file_to_item(file) -> dict:
    return {key: getattr(file, key, None) for key in FILE_FIELDS}


def folder_to_item(folder) -> dict:
    return {
        "id": folder.id,
        "name": folder.name,
        "extension": None,
        "size": 0,
        "mime_type": None,
        "folder_id": folder.parent_id,
        "created_at": str(folder.created_at) if folder.created_at else None,
        "updated_at": str(folder.created_at) if folder.created_at else None,
        "is_folder": True,
    }


def coerce_positive_int(value, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be an integer") from exc
    if parsed <= 0:
        raise ValidationError(f"{field_name} must be a positive integer")
    return parsed


def coerce_non_negative_int(value, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be an integer") from exc
    if parsed < 0:
        raise ValidationError(f"{field_name} must be non-negative")
    return parsed


def coerce_page(value) -> int:
    return coerce_positive_int(value if value is not None else 1, "page")


def coerce_page_size(value) -> int:
    page_size = coerce_positive_int(value if value is not None else 50, "page_size")
    if page_size > MAX_PAGE_SIZE:
        raise ValidationError(f"page_size must be <= {MAX_PAGE_SIZE}")
    return page_size


def normalize_extension(value) -> str | None:
    if value is None:
        return None
    ext = str(value).strip().lower().lstrip(".")
    if not ext:
        return None
    if "/" in ext or "\\" in ext or ".." in ext:
        raise ValidationError("extension must be a simple file extension")
    return ext


def normalize_file_name(value) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValidationError("name is required")
    if "/" in name or "\\" in name or ".." in name:
        raise ValidationError("name must not contain path separators")
    return name


def truncate_text(text: str, max_chars: int = MAX_READ_CHARS) -> tuple[str, dict]:
    original_chars = len(text)
    truncated = original_chars > max_chars
    returned = text[:max_chars] if truncated else text
    return returned, {
        "truncated": truncated,
        "content_chars": original_chars,
        "returned_chars": len(returned),
        "max_chars": max_chars,
    }


def limit_blocks(blocks: list[dict], max_chars: int = MAX_READ_CHARS) -> tuple[list[dict], dict]:
    limited: list[dict] = []
    used_chars = 0
    original_chars = 0
    truncated = len(blocks) > MAX_READ_BLOCKS

    for block in blocks:
        text = block.get("text")
        text_len = len(text) if isinstance(text, str) else 0
        original_chars += text_len
        if len(limited) >= MAX_READ_BLOCKS:
            truncated = True
            continue

        copied = deepcopy(block)
        if isinstance(text, str):
            remaining = max_chars - used_chars
            if remaining <= 0:
                truncated = True
                break
            if text_len > remaining:
                copied["text"] = text[:remaining]
                used_chars += remaining
                truncated = True
            else:
                used_chars += text_len
        limited.append(copied)

    return limited, {
        "truncated": truncated,
        "content_chars": original_chars,
        "returned_chars": used_chars,
        "max_chars": max_chars,
        "max_blocks": MAX_READ_BLOCKS,
    }
