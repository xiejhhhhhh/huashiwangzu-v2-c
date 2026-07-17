"""Canonical Normalizer —— parser 输出 + 三套 legacy IR → CanonicalContentIRV1(方案07 §19.2, WP3)。

单一归一入口。把「第四种事实结构」(package_service 产出的 {manifest, blocks} content_json)
和三套 legacy IR(ContentPackageIR / DocumentIR / Knowledge DocumentIr)统一收敛成
CanonicalContentIRV1(扁平 nodes + parent_id/order + 格式 Profile + 资源分片)。

固定规则(§19.2):
  - nodes 只保存扁平数组,parent_id + order 表树,不再存递归 children。
  - 新解析节点用 UUIDv7;legacy 迁移用基于旧对象身份的确定性 UUIDv5(节点跨版本稳定)。
  - profile_data 按 6 种 profile 填必填键骨架(结构校验必过),缺的键给默认空值不省略。
  - fidelity 保守判定:导入文件本轮一律 editable=false(未过往返保真门禁,只读),不假绿。
  - deferred 项(图像 VLM 描述 / OCR / ASR)记 diagnostics,不静默丢弃。
  - extensions 只放命名空间键(legacy.content_package / legacy.knowledge / ...)。

本轮(§24)纯结构转换,不调任何模型;需 VLM 的格式落 metadata_only + deferred diagnostic。
"""
from __future__ import annotations

import logging
from typing import Any

from app.contracts.canonical_content_ir import (
    PROFILE_REQUIRED_KEYS,
    CanonicalContentIRV1,
    ContentProfile,
    IRDiagnostic,
    IRFidelity,
    IRMetadata,
    IRNode,
    IRResourceRef,
    IRSource,
)
from app.contracts.ids import deterministic_uuid5, new_uuid7

logger = logging.getLogger("v2.content").getChild("canonical_normalizer")

# parser/legacy 的英文 block type → canonical node kind。canonical kind 是自由字符串,
# 这里只做少量别名收敛,未知 type 原样保留(不静默丢)。
_KIND_ALIASES: dict[str, str] = {
    "text": "paragraph",
    "section": "heading",
    "list_item": "list",
    "divider": "separator",
    "figure": "image",
    "textbox": "paragraph",
    "page_break": "separator",
}

# 扩展名 / 格式 → canonical profile(6 种)。text→document,image/audio/video→media。
_SPREADSHEET_FORMATS = {"csv", "tsv", "xlsx", "xls", "xlsm"}
_PRESENTATION_FORMATS = {"pptx", "ppt"}
_PDF_FORMATS = {"pdf"}
_MEDIA_FORMATS = {
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "ico", "svg", "tiff", "image",
    "mp3", "wav", "flac", "aac", "ogg", "m4a", "audio",
    "mp4", "mov", "avi", "mkv", "webm", "video",
}
_DOCUMENT_FORMATS = {"docx", "doc", "txt", "md", "markdown", "rtf", "odt"}

def infer_profile(extension: str | None, package_type: str | None, content_type: str | None) -> ContentProfile:
    """按扩展名/包类型/content_type 推断 canonical profile。优先级:扩展名 > 类型声明。"""
    ext = (extension or "").lower().lstrip(".")
    if ext in _SPREADSHEET_FORMATS:
        return "spreadsheet"
    if ext in _PRESENTATION_FORMATS:
        return "presentation"
    if ext in _PDF_FORMATS:
        return "pdf"
    if ext in _MEDIA_FORMATS:
        return "media"
    if ext in _DOCUMENT_FORMATS:
        return "document"
    # 扩展名不认识时看类型声明
    declared = (package_type or content_type or "").lower()
    if declared in ("spreadsheet", "presentation", "pdf", "media", "document"):
        return declared  # type: ignore[return-value]
    if declared in ("image", "audio", "video"):
        return "media"
    if declared == "text":
        return "document"
    return "generic"


def _kind_of(raw_type: Any) -> str:
    t = str(raw_type or "paragraph").strip().lower()
    return _KIND_ALIASES.get(t, t)


def normalize_content_dict(
    content: dict[str, Any],
    *,
    source: IRSource,
    profile: ContentProfile,
    node_id_seed: str | None = None,
) -> CanonicalContentIRV1:
    """把 package_service 产出的 {manifest, blocks[, parse_status, resource_diagnostics]}
    归一成 CanonicalContentIRV1。

    node_id_seed:
      - None(默认,新解析) → 新节点用 UUIDv7。
      - 非空(legacy 迁移) → 节点用 deterministic_uuid5(seed, block_path),跨版本稳定。
    """
    manifest = content.get("manifest") if isinstance(content.get("manifest"), dict) else {}
    raw_blocks = content.get("blocks") if isinstance(content.get("blocks"), list) else []

    nodes: list[IRNode] = []
    resource_refs: list[IRResourceRef] = []
    diagnostics: list[IRDiagnostic] = []

    # 递归拍平 blocks → 扁平 nodes(parent_id + order),同时抽 resource_ref。
    _flatten_blocks(
        raw_blocks, parent_id=None, nodes=nodes, resource_refs=resource_refs,
        node_id_seed=node_id_seed, path_prefix="",
    )

    metadata = IRMetadata(
        title=str(manifest.get("title") or source.original_name or ""),
        properties={
            k: manifest[k] for k in ("page_count", "sheet_count", "slide_count", "parser_version")
            if k in manifest
        },
    )

    profile_data = _build_profile_data(profile, manifest, nodes, content)
    fidelity = _judge_fidelity(profile, content, nodes)

    parse_status = str(content.get("parse_status") or "")
    if parse_status == "skipped":
        diagnostics.append(IRDiagnostic(
            code="parse_skipped", severity="warning",
            message=str(content.get("deferred_reason") or "parse skipped"), recoverable=True,
        ))
    for diag in content.get("resource_diagnostics") or []:
        if isinstance(diag, dict):
            diagnostics.append(IRDiagnostic(
                code=str(diag.get("code") or "resource_diagnostic"),
                severity="warning", message=str(diag.get("message") or diag)[:500], recoverable=True,
            ))

    return CanonicalContentIRV1(
        profile=profile, source=source, metadata=metadata,
        nodes=nodes, resource_refs=resource_refs, profile_data=profile_data,
        fidelity=fidelity, diagnostics=diagnostics,
    )


# ── 递归拍平:blocks(可能带 children)→ 扁平 nodes(parent_id + order) ──────────

def _flatten_blocks(
    blocks: list[Any], *, parent_id: str | None, nodes: list[IRNode],
    resource_refs: list[IRResourceRef], node_id_seed: str | None, path_prefix: str,
) -> None:
    """深度优先拍平。order 用同级序号(float),树关系只靠 parent_id + order。

    resource_ref(int,指向 framework_resources.id)就地建 IRResourceRef,anchor 到本节点。
    """
    for idx, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        path = f"{path_prefix}/{idx}"
        # 节点 id:迁移用确定性 uuid5(seed+path 或旧 block id),新解析用 uuid7。
        if node_id_seed is not None:
            legacy_bid = block.get("id")
            node_id = deterministic_uuid5(node_id_seed, legacy_bid if legacy_bid else path)
        else:
            node_id = new_uuid7()

        kind = _kind_of(block.get("type"))
        attrs = dict(block.get("data") or {})
        # page/slide/sheet 等定位信息保留进 attrs(canonical 不再有顶层 page 字段)。
        for loc_key in ("page", "slide", "sheet", "level", "hierarchy_level", "coordinate"):
            if block.get(loc_key) is not None:
                attrs.setdefault(loc_key, block[loc_key])

        node = IRNode(
            id=node_id, kind=kind, parent_id=parent_id, order=float(idx),
            text=str(block.get("text") or ""),
            attrs=attrs,
            style=dict(block.get("style") or {}),
            provenance=dict(block.get("source_ref") or {}),
        )
        nodes.append(node)

        # 资源引用:block.resource_ref 是真实 framework_resources.id(package_service 已回填)。
        res_id = block.get("resource_ref")
        if isinstance(res_id, int) and res_id > 0:
            resource_refs.append(IRResourceRef(
                ref_id=deterministic_uuid5(node_id, "res", res_id) if node_id_seed
                else new_uuid7(),
                resource_id=res_id, role="embedded",
                anchor_type="node", anchor_id=node_id,
            ))

        children = block.get("children")
        if isinstance(children, list) and children:
            _flatten_blocks(
                children, parent_id=node_id, nodes=nodes, resource_refs=resource_refs,
                node_id_seed=node_id_seed, path_prefix=path,
            )


# ── profile_data 骨架:6 种 profile 填必填键(缺的给默认空值,结构校验必过) ──────

def _build_profile_data(
    profile: ContentProfile, manifest: dict[str, Any],
    nodes: list[IRNode], content: dict[str, Any],
) -> dict[str, Any]:
    """按 PROFILE_REQUIRED_KEYS 填齐必填键。本轮只填结构骨架(不调模型),
    深度字段(ocr_layers/transcript 等)给默认空值 + 标 deferred,不省略、不假填。
    """
    required = PROFILE_REQUIRED_KEYS.get(profile, ())
    data: dict[str, Any] = {k: _default_for_key(k) for k in required}

    if profile == "document":
        data["sections"] = [{"node_id": n.id, "title": n.text} for n in nodes if n.kind == "heading"]
    elif profile == "spreadsheet":
        data["sheets"] = [{"node_id": n.id, "name": n.text} for n in nodes if n.kind == "sheet"]
        data["workbook"] = {"sheet_count": manifest.get("sheet_count", len(data["sheets"]))}
    elif profile == "presentation":
        data["slides"] = [{"node_id": n.id, "index": n.attrs.get("slide") or n.attrs.get("page")}
                          for n in nodes if n.kind == "slide"]
        data["page_size"] = {}
    elif profile == "pdf":
        data["pages"] = sorted({int(n.attrs["page"]) for n in nodes if isinstance(n.attrs.get("page"), int)})
        # OCR/图像层本轮越过模型,留空骨架 + deferred 标记(见 diagnostics)。
    elif profile == "media":
        data["derivatives"] = []
        # transcript/tracks 需 ASR/VLM,本轮 deferred,留空。
    elif profile == "generic":
        data["detected_type"] = manifest.get("extension") or ""
        data["download_capability"] = True

    return data


def _default_for_key(key: str) -> Any:
    """必填键的默认空值:复数/列表语义给 [],单数/配置给 {}。"""
    list_like = (
        "sections", "headers", "footers", "footnotes", "sheets", "sheet_parts",
        "defined_names", "slides", "elements", "notes", "masters", "layouts",
        "pages", "text_spans", "images", "annotations", "forms", "ocr_layers",
        "rendered_pages", "streams", "tracks", "markers", "derivatives", "preview_refs",
    )
    return [] if key in list_like else ({} if key not in ("download_capability",) else False)


# ── fidelity 判定:保守,导入文件本轮一律 editable=false(未过往返保真门禁) ──────

def _judge_fidelity(profile: ContentProfile, content: dict[str, Any], nodes: list[IRNode]) -> IRFidelity:
    """本轮 §24:所有导入文件只读(editable=false),不做往返保真承诺。

    level 按解析完整度:有正文结构→structural;只有文本→textual;跳过/空→metadata_only。
    """
    parse_status = str(content.get("parse_status") or "")
    if parse_status == "skipped" or not nodes:
        level = "metadata_only"
    elif profile in ("document", "text") and all(n.kind in ("heading", "paragraph", "list", "code", "quote", "separator") for n in nodes):
        level = "textual"
    else:
        level = "structural"

    unsupported: list[str] = []
    if profile == "pdf":
        unsupported.append("ocr_layers(model_budget_deferred)")
    if profile == "media":
        unsupported.append("transcript(model_budget_deferred)")
    return IRFidelity(
        level=level, editable=False,  # §24: 导入文件本轮一律只读
        supported_features=["read", "structural_view"],
        unsupported_features=unsupported,
    )


# ── 对外主入口 ─────────────────────────────────────────────────────────────

def normalize_parser_output(
    parser_output: dict[str, Any], *,
    file_id: int | None, extension: str, source_sha256: str | None = None,
    original_name: str = "", mime_type: str = "", size: int = 0,
) -> CanonicalContentIRV1:
    """新解析主路径:parser raw dict(或 package_service 的 {manifest,blocks})→ CanonicalContentIRV1。

    新节点用 UUIDv7(node_id_seed=None)。这是 canonical_parse 双写调用的入口。
    """
    manifest = parser_output.get("manifest") if isinstance(parser_output.get("manifest"), dict) else {}
    ext = (extension or manifest.get("extension") or parser_output.get("format") or "").lower().lstrip(".")
    profile = infer_profile(ext, manifest.get("package_type"), parser_output.get("content_type"))
    source = IRSource(
        file_id=file_id, original_name=original_name or manifest.get("title") or "",
        extension=ext, mime_type=mime_type, size=size, sha256=source_sha256,
    )
    return normalize_content_dict(parser_output, source=source, profile=profile, node_id_seed=None)


def normalize_legacy_content_package_ir(
    content_json: dict[str, Any], *, package_id: int, file_id: int | None, extension: str,
) -> CanonicalContentIRV1:
    """迁移优先级 §19.2 第2档:现有 ContentPackageIR / 写库的 {manifest,blocks} → canonical。

    节点用 deterministic_uuid5("content_package:{package_id}", ...),跨版本稳定。
    """
    manifest = content_json.get("manifest") if isinstance(content_json.get("manifest"), dict) else {}
    ext = (extension or manifest.get("extension") or "").lower().lstrip(".")
    profile = infer_profile(ext, manifest.get("package_type"), None)
    source = IRSource(
        file_id=file_id, original_name=str(manifest.get("title") or ""), extension=ext,
    )
    ir = normalize_content_dict(
        content_json, source=source, profile=profile,
        node_id_seed=f"content_package:{package_id}",
    )
    ir.extensions["legacy.content_package"] = {"package_id": package_id, "migrated": True}
    return ir


def normalize_legacy_knowledge_ir(
    doc_ir: dict[str, Any], *, file_id: int | None, extension: str,
) -> CanonicalContentIRV1:
    """迁移优先级 §19.2 第4档:Knowledge DocumentIr(小写,递归 children + 中英 type)→ canonical。

    Knowledge 的 type 已是英文(from_legacy_blocks 转过),这里 _kind_of 再收敛别名即可。
    节点用 deterministic_uuid5("knowledge_doc:{file_id}", ...)。
    """
    ext = (extension or doc_ir.get("format") or "").lower().lstrip(".")
    profile = infer_profile(ext, None, None)
    source = IRSource(
        file_id=file_id or doc_ir.get("file_id"),
        original_name=str(doc_ir.get("source_filename") or ""),
        extension=ext, size=int(doc_ir.get("source_size") or 0),
    )
    # DocumentIr 顶层是 blocks/resources,包成 content_dict 复用主路径。
    content = {"manifest": {"title": doc_ir.get("source_filename") or ""}, "blocks": doc_ir.get("blocks") or []}
    ir = normalize_content_dict(
        content, source=source, profile=profile,
        node_id_seed=f"knowledge_doc:{file_id or doc_ir.get('file_id')}",
    )
    ir.extensions["legacy.knowledge"] = {"migrated": True, "parse_status": doc_ir.get("parse_status")}
    return ir

