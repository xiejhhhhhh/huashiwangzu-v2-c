"""Content Package Intermediate Representation (IR) schemas.

All parsers produce this structure. All consumers (knowledge, agent, export)
consume only this IR.

ContentPackage is the canonical source for all structured content in V2.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PackageType = Literal[
    "document", "spreadsheet", "presentation", "pdf",
    "image", "text", "media", "generic",
]

BlockType = Literal[
    "heading", "paragraph", "table", "list", "code",
    "image", "figure", "formula", "quote", "separator",
    "slide", "textbox", "cell", "sheet", "page", "media",
]


class Coordinate(BaseModel):
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0


class ResourceRefSchema(BaseModel):
    resource_id: int
    usage_type: str = "embedded"
    page: int | None = None
    coordinates: Coordinate | None = None
    usage_hints: str | None = None


class ContentBlockSchema(BaseModel):
    id: str = ""
    type: BlockType = "paragraph"
    page: int | None = None
    parent_id: str | None = None
    order: int = 0
    text: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)
    resource_refs: list[ResourceRefSchema] = Field(default_factory=list)
    children: list[ContentBlockSchema] = Field(default_factory=list)

    def iter_all(self) -> list[ContentBlockSchema]:
        result: list[ContentBlockSchema] = []
        stack = list(self.children)
        result.append(self)
        while stack:
            b = stack.pop(0)
            result.append(b)
            if b.children:
                stack = b.children + stack
        return result


class ContentManifest(BaseModel):
    title: str = ""
    source_file_id: int = 0
    extension: str = ""
    package_type: PackageType = "generic"
    page_count: int = 0
    sheet_count: int = 0
    slide_count: int = 0
    created_by_parser: str = ""
    parser_version: str = "1.0"
    source_hash: str = ""


class ContentPackageIR(BaseModel):
    manifest: ContentManifest = Field(default_factory=ContentManifest)
    blocks: list[ContentBlockSchema] = Field(default_factory=list)

    def iter_all_blocks(self) -> list[ContentBlockSchema]:
        result: list[ContentBlockSchema] = []
        stack = list(self.blocks)
        while stack:
            b = stack.pop(0)
            result.append(b)
            if b.children:
                stack = b.children + stack
        return result

    def find_block(self, block_id: str) -> ContentBlockSchema | None:
        for b in self.iter_all_blocks():
            if b.id == block_id:
                return b
        return None


class PackageSummary(BaseModel):
    id: int
    owner_id: int
    source_file_id: int | None
    package_type: str
    source_extension: str
    status: str
    publish_status: str = "draft_package"
    published_artifact_id: int | None = None
    published_file_id: int | None = None
    published_version_id: int | None = None
    download_url: str | None = None
    current_version_id: int | None
    manifest_json: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VersionSummary(BaseModel):
    id: int
    package_id: int
    version_no: int
    summary: str | None
    operation_type: str
    created_by: int
    created_at: datetime | None = None


class ResourceSummary(BaseModel):
    id: int
    hash: str
    resource_type: str
    mime_type: str
    storage_path: str
    file_size: int
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    description: str | None = None
    ocr_text: str | None = None
    ref_count: int
    created_at: datetime | None = None


class ResourceRefSummary(BaseModel):
    id: int
    resource_id: int
    block_id: str | None
    usage_type: str
    page: int | None
    coordinates: dict | None = None
    usage_hints: str | None = None


class BlockUpdateRequest(BaseModel):
    block_id: str
    text: str | None = None
    data: dict[str, Any] | None = None
    style: dict[str, Any] | None = None


class BlockAppendRequest(BaseModel):
    parent_id: str | None = None
    after_block_id: str | None = None
    type: BlockType = "paragraph"
    text: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)


class ReplaceTextRequest(BaseModel):
    old_text: str
    new_text: str
    scope: str = "all"


class ExportRequest(BaseModel):
    target_format: str | None = None
    conflict_policy: str = "auto_rename"


class PublishRequest(BaseModel):
    target_file_id: int | None = None
    conflict_policy: str = "create_version"


class PublishResponse(BaseModel):
    package_id: int
    artifact_id: int
    file_id: int
    download_url: str | None = None
    published_version_id: int | None = None
    status: str
    publish_status: str = "published_artifact/file"
    target_file_id: int | None = None
    published: bool = True
