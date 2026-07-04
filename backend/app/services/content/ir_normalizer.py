"""Content IR normalizer — fills in defaults, block ids, resource refs.

Called after validation passes. Produces a complete, normalized IR
ready for write_ir.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("v2.content").getChild("ir_normalizer")


def normalize_parser_output(
    parser_output: dict[str, Any],
    *,
    module: str,
    filename: str | None = None,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Convert parser legacy output into canonical Content IR.

    Parser capabilities historically return ``{file_id, format, blocks, resources}``.
    This adapter is the single compatibility gate used before validate/write, so
    downstream Artifact/Knowledge/Agent evidence can rely on one source shape.
    """
    source = _build_source(parser_output, module, filename, mime_type)
    raw_blocks = parser_output.get("blocks")
    blocks = [_normalize_parser_block(block, source) for block in raw_blocks if isinstance(block, dict)] \
        if isinstance(raw_blocks, list) else []
    raw_resources = parser_output.get("resources")
    resources = [_normalize_parser_resource(resource) for resource in raw_resources if isinstance(resource, dict)] \
        if isinstance(raw_resources, list) else []

    content_type = _infer_content_type(parser_output, module, blocks, resources)
    blocks = _shape_blocks_for_profile(content_type, blocks, parser_output, source)

    title = str(
        parser_output.get("title")
        or filename
        or source.get("filename")
        or f"{module} parse result"
    )
    ir = {
        "schema_version": parser_output.get("schema_version") or "1.0",
        "content_type": content_type,
        "title": title,
        "source_file_id": source.get("file_id"),
        "source_module": module,
        "parser": f"{module}:parse",
        "source": source,
        "metadata": _build_parser_metadata(parser_output),
        "blocks": blocks,
        "resources": resources,
        "assets": list(resources),
        "warnings": parser_output.get("warnings", []),
        "quality": _build_parser_quality(parser_output),
    }
    return ir


async def normalize_ir(content_ir: dict[str, Any]) -> dict[str, Any]:
    """Normalize a validated Content IR in-place and return it.

    - Ensure schema_version defaults to '1.0'
    - Ensure locale defaults to 'zh-CN'
    - Ensure metadata is a dict
    - Auto-generate block ids for blocks without id
    - Normalize resource ids
    - Add defaults from content_type profile
    """
    ir = dict(content_ir)

    ir.setdefault("schema_version", "1.0")
    ir.setdefault("locale", "zh-CN")
    ir.setdefault("metadata", {})
    ir.setdefault("warnings", [])
    ir.setdefault("quality", {})
    if "resources" not in ir and isinstance(ir.get("assets"), list):
        ir["resources"] = list(ir["assets"])
    ir.setdefault("resources", [])

    # Normalize blocks recursively
    blocks = ir.get("blocks", [])
    _normalize_blocks(blocks)

    # Normalize resources
    resources = ir.get("resources", [])
    used_resource_ids: set[str | int] = set()
    for res in resources:
        rid = res.get("id")
        if rid is None or str(rid) in used_resource_ids:
            rid = f"r{hashlib.sha256(json.dumps(res, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]}"
            res["id"] = rid
        used_resource_ids.add(str(rid))
        res.setdefault("resource_type", "image")
        res.setdefault("mime_type", "application/octet-stream")
        res.setdefault("filename", "")

    ir["blocks"] = blocks
    ir["resources"] = resources
    ir["assets"] = list(resources)
    return ir


def _normalize_blocks(blocks: list[dict]) -> None:
    for i, block in enumerate(blocks):
        if not block.get("id"):
            raw = f"{i}:{block.get('text', '')}:{block.get('type', '')}:{datetime.now(timezone.utc).timestamp()}"
            block["id"] = f"b{hashlib.md5(raw.encode()).hexdigest()[:12]}"
        block.setdefault("data", {})
        block.setdefault("style", {})

        children = block.get("children")
        if isinstance(children, list):
            _normalize_blocks(children)


def _build_source(
    parser_output: dict[str, Any],
    module: str,
    filename: str | None,
    mime_type: str | None,
) -> dict[str, Any]:
    existing_source = parser_output.get("source")
    source = dict(existing_source) if isinstance(existing_source, dict) else {}
    source.setdefault("module", module)
    source.setdefault("file_id", parser_output.get("file_id"))
    source.setdefault("filename", filename or parser_output.get("filename"))
    source.setdefault("mime_type", mime_type or parser_output.get("mime_type"))
    source.setdefault("format", parser_output.get("format") or parser_output.get("media_type"))
    return source


def _normalize_parser_block(block: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(block)
    normalized["type"] = _normalize_block_type(str(normalized.get("type") or "paragraph"))
    normalized["text"] = str(normalized.get("text") or "")
    source_ref = dict(normalized.get("source_ref") or {})
    if normalized.get("page") is not None:
        source_ref.setdefault("page", normalized.get("page"))
    if normalized.get("resource_ref") is not None:
        source_ref.setdefault("resource_ref", normalized.get("resource_ref"))
    if source.get("file_id") is not None:
        source_ref.setdefault("file_id", source.get("file_id"))
    if source.get("module"):
        source_ref.setdefault("module", source.get("module"))
    if source_ref:
        normalized["source_ref"] = source_ref
    normalized.setdefault("metadata", {})
    normalized.setdefault("data", {})
    return normalized


def _normalize_block_type(block_type: str) -> str:
    aliases = {
        "text": "paragraph",
        "metadata": "paragraph",
        "section": "heading",
        "page": "paragraph",
        "message": "paragraph",
        "transcript": "paragraph",
        "error": "paragraph",
    }
    return aliases.get(block_type, block_type)


def _normalize_parser_resource(resource: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(resource)
    if "resource_type" not in normalized:
        normalized["resource_type"] = normalized.get("type") or "image"
    if "data_b64" not in normalized and normalized.get("_bytes_b64"):
        normalized["data_b64"] = normalized.get("_bytes_b64")
    if "description" not in normalized and normalized.get("text_desc"):
        normalized["description"] = normalized.get("text_desc")
    normalized.setdefault("mime_type", "application/octet-stream")
    normalized.setdefault("filename", "")
    return {
        key: value
        for key, value in normalized.items()
        if not str(key).startswith("_")
    }


def _infer_content_type(
    parser_output: dict[str, Any],
    module: str,
    blocks: list[dict[str, Any]],
    resources: list[dict[str, Any]],
) -> str:
    declared_type = parser_output.get("content_type")
    fmt = str(parser_output.get("format") or parser_output.get("media_type") or "").lower()
    if module in {"csv-parser", "xlsx-parser"} or fmt in {"csv", "tsv", "xlsx"}:
        return "spreadsheet"
    if module == "pptx-parser" or fmt == "pptx":
        return "presentation"
    if module == "image-vision" or fmt in {"jpg", "jpeg", "png", "gif", "webp", "bmp", "ico", "image"}:
        return "image"
    if module == "media-intelligence":
        return "image" if fmt == "image" or parser_output.get("media_type") == "image" else "mixed"
    if module == "text-parser" or fmt == "txt":
        return "text"
    if module == "markdown-parser" or fmt in {"md", "markdown"}:
        return str(declared_type) if declared_type in {"document", "mixed", "text"} else ("mixed" if resources else "document")
    if declared_type in {"document", "presentation", "spreadsheet", "text", "image", "mixed", "memory"}:
        return str(declared_type)
    if resources and any(block.get("resource_ref") is not None for block in blocks):
        return "mixed"
    return "document"


def _shape_blocks_for_profile(
    content_type: str,
    blocks: list[dict[str, Any]],
    parser_output: dict[str, Any],
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    if content_type == "spreadsheet":
        return _shape_spreadsheet_blocks(blocks, parser_output, source)
    if content_type == "presentation":
        return _shape_presentation_blocks(blocks, parser_output, source)
    if content_type == "image":
        return _shape_image_blocks(blocks, parser_output, source)
    if content_type == "text":
        return [
            block for block in blocks
            if block.get("type") in {"heading", "paragraph", "code", "list", "quote"}
        ] or [_empty_block(source)]
    return blocks or [_empty_block(source)]


def _shape_spreadsheet_blocks(
    blocks: list[dict[str, Any]],
    parser_output: dict[str, Any],
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    sheet_children = []
    for block in blocks:
        if block.get("type") == "sheet":
            sheet_children.extend(block.get("children") if isinstance(block.get("children"), list) else [])
        elif block.get("type") == "table":
            sheet_children.append(block)
        elif block.get("text"):
            sheet_children.append({**block, "type": "table"})
    sheet_name = str(parser_output.get("sheet_name") or parser_output.get("format") or "Sheet1")
    return [{
        "type": "sheet",
        "text": sheet_name,
        "source_ref": {"file_id": source.get("file_id"), "sheet": sheet_name},
        "children": sheet_children,
    }]


def _shape_presentation_blocks(
    blocks: list[dict[str, Any]],
    parser_output: dict[str, Any],
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    slides: dict[int, list[dict[str, Any]]] = {}
    for block in blocks:
        slide_no = int(block.get("page") or block.get("slide") or 1)
        child = dict(block)
        child.pop("page", None)
        slides.setdefault(slide_no, []).append(child)
    if not slides:
        slides[1] = [_empty_block(source)]
    return [
        {
            "type": "slide",
            "text": f"Slide {slide_no}",
            "source_ref": {"file_id": source.get("file_id"), "slide": slide_no},
            "children": children,
        }
        for slide_no, children in sorted(slides.items())
    ]


def _shape_image_blocks(
    blocks: list[dict[str, Any]],
    parser_output: dict[str, Any],
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    image_blocks = [block for block in blocks if block.get("type") == "image"]
    if image_blocks:
        return image_blocks
    summary = str(parser_output.get("description") or parser_output.get("summary") or "")
    return [{
        "type": "image",
        "text": summary,
        "source_ref": {"file_id": source.get("file_id"), "image": True},
        "data": {},
    }]


def _empty_block(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "text": "",
        "source_ref": {"file_id": source.get("file_id"), "empty": True},
        "metadata": {"empty": True},
    }


def _build_parser_metadata(parser_output: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(parser_output.get("metadata") or {})
    for key in (
        "format", "resource_diagnostics", "analysis_strategy", "model_fallback",
        "degraded_reasons", "local_analysis", "artifacts", "stages", "signals",
        "tags", "confidence", "action", "media_type",
    ):
        if key in parser_output and key not in metadata:
            metadata[key] = parser_output[key]
    return metadata


def _build_parser_quality(parser_output: dict[str, Any]) -> dict[str, Any]:
    quality: dict[str, Any] = {}
    confidence = parser_output.get("confidence")
    if isinstance(confidence, int | float):
        quality["confidence"] = float(confidence)
    model_fallback = parser_output.get("model_fallback")
    if isinstance(model_fallback, dict):
        quality["model_fallback"] = model_fallback
    return quality
