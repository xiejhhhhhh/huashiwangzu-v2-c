"""Content IR unified schema definitions.

Uniform intermediate representation for all structured content.
Agent/parser produces this; validator/normalizer/writer consume this.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ContentType = Literal[
    "document", "presentation", "spreadsheet",
    "text", "image", "mixed", "memory",
]

BlockType = Literal[
    "heading", "paragraph", "list", "table", "sheet",
    "range", "cell_patch", "slide", "image", "chart",
    "code", "quote", "divider",
]

CONTENT_TYPE_VALUES: set[str] = {
    "document", "presentation", "spreadsheet",
    "text", "image", "mixed", "memory",
}

BLOCK_TYPE_VALUES: set[str] = {
    "heading", "paragraph", "list", "table", "sheet",
    "range", "cell_patch", "slide", "image", "chart",
    "code", "quote", "divider",
}


class ContentBlock(BaseModel):
    id: str = ""
    type: str = "paragraph"
    text: str = ""
    level: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)
    children: list[ContentBlock] = Field(default_factory=list)
    resource_ref: str | int | None = None


class ContentResource(BaseModel):
    id: str | int = ""
    resource_type: str = "image"
    mime_type: str = "application/octet-stream"
    filename: str = ""
    data_b64: str = ""
    description: str | None = None
    ocr_text: str | None = None
    vlm_metadata: dict[str, Any] | None = None
    width: int | None = None
    height: int | None = None


class ContentIR(BaseModel):
    schema_version: str = "1.0"
    content_type: str = "document"
    title: str = ""
    source_file_id: int | None = None
    source_module: str = ""
    parser: str = ""
    locale: str = "zh-CN"
    metadata: dict[str, Any] = Field(default_factory=dict)
    blocks: list[ContentBlock] = Field(default_factory=list)
    resources: list[ContentResource] = Field(default_factory=list)
    assets: list[ContentResource] = Field(default_factory=list)
    warnings: list[dict[str, Any] | str] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)


class ValidationError(BaseModel):
    path: str = ""
    code: str = ""
    message: str = ""
    expected: str = ""
    actual: str = ""


class ValidationResult(BaseModel):
    valid: bool = True
    errors: list[ValidationError] = Field(default_factory=list)
    normalized_preview: dict[str, Any] | None = None


# ── Profile rules ────────────────────────────────────────────────

CONTENT_TYPE_PROFILES: dict[str, dict[str, Any]] = {
    "document": {
        "allowed_top_blocks": {
            "heading", "paragraph", "list", "table",
            "image", "chart", "code", "quote", "divider",
        },
        "allowed_nested_blocks": {
            "heading", "paragraph", "list", "table",
            "image", "chart", "code", "quote", "divider",
        },
        "description": "Standard document with headings, paragraphs, tables, images",
    },
    "presentation": {
        "allowed_top_blocks": {"slide"},
        "allowed_nested_in_slide": {
            "heading", "paragraph", "list", "table",
            "image", "chart", "code", "quote", "divider",
        },
        "description": "Slide deck; top-level blocks must be slides",
    },
    "spreadsheet": {
        "allowed_top_blocks": {"sheet"},
        "allowed_nested_in_sheet": {
            "table", "range", "cell_patch",
        },
        "description": "Spreadsheet; top-level blocks must be sheets",
    },
    "text": {
        "allowed_top_blocks": {
            "heading", "paragraph", "code", "list", "quote",
        },
        "allowed_nested_blocks": set(),
        "description": "Plain text / markdown / code",
    },
    "image": {
        "allowed_top_blocks": {"image"},
        "allowed_nested_blocks": set(),
        "description": "Image with description, OCR, VLM metadata",
    },
    "mixed": {
        "allowed_top_blocks": {
            "heading", "paragraph", "list", "table",
            "image", "chart", "code", "quote", "divider",
        },
        "allowed_nested_blocks": {
            "heading", "paragraph", "list", "table",
            "image", "chart", "code", "quote", "divider",
        },
        "description": "Mixed-content document with embedded resources",
    },
    "memory": {
        "allowed_top_blocks": {
            "heading", "paragraph", "list", "code", "quote",
        },
        "allowed_nested_blocks": set(),
        "description": "Factual memory; no binary or style fields",
    },
}
