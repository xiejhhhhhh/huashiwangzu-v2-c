"""Generation parameter and rendering helpers for office-gen."""
from collections.abc import Callable

from app.core.exceptions import ValidationError

from .. import converter, generator

SUPPORTED_GENERATE_FORMATS = {"docx", "xlsx", "pptx", "pdf"}


def normalize_format(format_type: object) -> str:
    fmt = str(format_type or "").lower().lstrip(".").strip()
    if fmt not in SUPPORTED_GENERATE_FORMATS:
        raise ValidationError(f"Unsupported format: {fmt or '<empty>'}")
    return fmt


def normalize_convert_format(format_type: object) -> str:
    fmt = str(format_type or "").lower().lstrip(".").strip()
    if not fmt:
        raise ValidationError("target_format is required")
    if fmt not in converter.SUPPORTED_FORMATS:
        supported = ", ".join(sorted(converter.SUPPORTED_FORMATS))
        raise ValidationError(f"Unsupported target_format: {fmt}. Supported: {supported}")
    return fmt


def positive_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValidationError(f"{name} must be a positive integer")
    return parsed


def optional_positive_int(value: object, name: str) -> int | None:
    if value is None or value == "":
        return None
    return positive_int(value, name)


def require_non_empty_list(params: dict, key: str, aliases: tuple[str, ...] = ()) -> list:
    for candidate in (key, *aliases):
        value = params.get(candidate)
        if isinstance(value, list) and value:
            return value
        content_ir = params.get("content_ir")
        if isinstance(content_ir, dict):
            value = content_ir.get(candidate)
            if isinstance(value, list) and value:
                return value
    raise ValidationError(f"{key} must be a non-empty array")


def render_generated_bytes(render: Callable[[], bytes]) -> bytes:
    try:
        return render()
    except (RuntimeError, ValueError) as exc:
        raise ValidationError(str(exc)) from exc


def generate_bytes_for_format(format_type: str, filename: str, params: dict) -> bytes:
    fmt = normalize_format(format_type)
    if fmt == "xlsx":
        sheets = require_non_empty_list(params, "sheets", ("工作表", "blocks"))
        return render_generated_bytes(lambda: generator.generate_xlsx({"filename": filename, "sheets": sheets}))
    if fmt == "docx":
        content = require_non_empty_list(params, "content", ("blocks",))
        return render_generated_bytes(lambda: generator.generate_docx({"filename": filename, "content": content}))
    if fmt == "pptx":
        slides = require_non_empty_list(params, "slides", ("幻灯片", "blocks"))
        return render_generated_bytes(lambda: generator.generate_pptx({"filename": filename, "slides": slides}))
    content = require_non_empty_list(params, "content", ("blocks",))
    return render_generated_bytes(lambda: generator.generate_pdf({"filename": filename, "content": content}))
