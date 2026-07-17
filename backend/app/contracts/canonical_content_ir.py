"""CanonicalContentIRV1 —— 统一内容中间表示(方案07 §19.2 冻结合同)。

采用"统一信封 + 统一语义节点 + 格式 Profile + 资源分片",不是用一棵通用
Block 树压扁所有格式。所有 Parser 输出经 Normalizer 写入本合同;Office、Agent、
Knowledge、Viewer、Editor 只引用本合同。

固定规则(§19.2):
  - nodes 只保存扁平数组,以 parent_id + order 表达树,不再同时存递归 children。
  - 新节点用 UUIDv7;旧数据迁移用基于旧对象身份的确定性 UUIDv5;节点跨版本稳定。
  - extensions 只允许命名空间键(如 legacy.knowledge、ooxml.preserved_parts),
    未知字段不得静默丢弃。
  - content_sha256 用 RFC 8785 规范化 JSON 后计算真实 SHA-256(见 content_hash.py)。
  - source.sha256 必须是原始字节 SHA-256,禁止 SHA256(MD5字符串) 旧实现。
  - 大型 spreadsheet/ppt/pdf 不把完整数据塞进单个 content_json;Version 保存
    manifest + 引用,sheet/range、slide payload、rendered page 作为版本化 Resource
    分片按需加载(profile_data 只放骨架与引用)。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "canonical-content-ir/v1"

ContentProfile = Literal[
    "document", "spreadsheet", "presentation", "pdf", "media", "generic",
]
CONTENT_PROFILE_VALUES: tuple[str, ...] = (
    "document", "spreadsheet", "presentation", "pdf", "media", "generic",
)

FidelityLevel = Literal["lossless", "structural", "textual", "metadata_only"]
FIDELITY_LEVEL_VALUES: tuple[str, ...] = (
    "lossless", "structural", "textual", "metadata_only",
)

DiagnosticSeverity = Literal["info", "warning", "error"]

AnchorType = Literal["document", "node", "page", "slide", "sheet", "range"]


class IRSource(BaseModel):
    """原始来源(指向 SourceFileRevision,而非编辑事实源)。"""
    file_id: int | None = None
    revision_id: int | None = None
    original_name: str = ""
    extension: str = ""
    mime_type: str = ""
    size: int = 0
    sha256: str | None = None  # 原始字节 SHA-256
    imported_at: datetime | None = None


class IRMetadata(BaseModel):
    title: str = ""
    locale: str | None = None
    author: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class IRNode(BaseModel):
    """统一语义节点。扁平数组,树关系靠 parent_id + order。"""
    id: str                              # UUIDv7(新) / UUIDv5(迁移)
    kind: str                            # heading/paragraph/table/cell/slide/...
    parent_id: str | None = None
    order: float = 0
    text: str = ""
    attrs: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class IRResourceRef(BaseModel):
    """内容对二进制资源的引用。anchor 定位到节点/页/幻灯片/工作表/区域。"""
    ref_id: str                          # 稳定 ref_key
    resource_id: int
    role: str = "embedded"               # embedded/thumbnail/rendered_page/...
    anchor_type: AnchorType = "document"
    anchor_id: str | None = None
    geometry: dict[str, Any] | None = None
    geometry_unit: str | None = None
    transform: dict[str, Any] | None = None
    alt_text: str | None = None


class IRFidelity(BaseModel):
    """保真声明。未达阈值的格式先只读(editable=false),不切 IR 编辑。"""
    level: FidelityLevel = "structural"
    editable: bool = False
    supported_features: list[str] = Field(default_factory=list)
    unsupported_features: list[str] = Field(default_factory=list)


class IRDiagnostic(BaseModel):
    code: str
    severity: DiagnosticSeverity = "info"
    path: str | None = None
    message: str = ""
    recoverable: bool = True


class CanonicalContentIRV1(BaseModel):
    """统一信封。Version.content_json 存本结构(大数据分片进 Resource)。"""
    schema_version: Literal["canonical-content-ir/v1"] = "canonical-content-ir/v1"
    profile: ContentProfile = "generic"
    source: IRSource = Field(default_factory=IRSource)
    metadata: IRMetadata = Field(default_factory=IRMetadata)
    nodes: list[IRNode] = Field(default_factory=list)
    resource_refs: list[IRResourceRef] = Field(default_factory=list)
    # 格式特有骨架与分片引用(不放完整大数据)
    profile_data: dict[str, Any] = Field(default_factory=dict)
    fidelity: IRFidelity = Field(default_factory=IRFidelity)
    diagnostics: list[IRDiagnostic] = Field(default_factory=list)
    # 仅允许命名空间键(legacy.knowledge / ooxml.preserved_parts / ...)
    extensions: dict[str, Any] = Field(default_factory=dict)

    def iter_children(self, parent_id: str | None) -> list[IRNode]:
        """按 order 返回某父节点的直接子节点(树关系只靠 parent_id+order)。"""
        return sorted(
            (n for n in self.nodes if n.parent_id == parent_id),
            key=lambda n: n.order,
        )


# --- 格式 Profile 必填结构与 V1 编辑边界(§19.2 冻结表,供 Normalizer 校验) ---
# 只声明契约,不在此实现解析。各 Profile 的 profile_data 必须至少含下列键。
PROFILE_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "document": (
        "sections", "page_settings", "style_catalog",
        "headers", "footers", "footnotes",
    ),
    "spreadsheet": (
        "workbook", "sheets", "sheet_parts", "defined_names",
        "calculations", "print_settings",
    ),
    "presentation": (
        "page_size", "theme", "masters", "layouts",
        "slides", "elements", "notes",
    ),
    "pdf": (
        "pages", "text_spans", "images", "annotations",
        "forms", "ocr_layers", "rendered_pages",
    ),
    "media": (
        "streams", "duration", "dimensions", "tracks",
        "transcript", "markers", "derivatives",
    ),
    "generic": (
        "detected_type", "preview_refs", "metadata", "download_capability",
    ),
}

# spreadsheet 单元格至少保存的字段(§19.2)。
SPREADSHEET_CELL_MIN_FIELDS: tuple[str, ...] = (
    "address", "value_type", "value", "formula", "cached_value",
    "style_ref", "number_format", "hyperlink", "comment",
)


def validate_profile_data(ir: CanonicalContentIRV1) -> list[str]:
    """返回 profile_data 缺失的必填键列表(空列表=通过)。仅结构校验,不判语义。"""
    required = PROFILE_REQUIRED_KEYS.get(ir.profile, ())
    return [k for k in required if k not in ir.profile_data]


# 旧 IR 迁移优先级(§19.2,数值越小优先级越高)。
LEGACY_IR_MIGRATION_PRIORITY: tuple[str, ...] = (
    "resParse",              # 按 SourceFileRevision 重新解析(最高)
    "content_package_ir",    # 现有 ContentPackageIR
    "platform_document_ir",  # 平台 DocumentIR
    "knowledge_document_ir", # Knowledge DocumentIr
    "excel_legacy_state",    # Excel 旧状态抢救(最低)
)
