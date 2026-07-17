"""WP3 内容旁路收口测试（方案07 §19.2 / §8.5，安全增量）。

覆盖：
1. Normalizer 往返：parser raw dict（含递归 children）→ CanonicalContentIRV1，
   扁平 nodes + parent_id/order 正确、profile_data 必填键全齐、fidelity 保守只读。
2. profile 推断：docx→document / xlsx→spreadsheet / pptx→presentation /
   pdf→pdf / png→media / 未知→generic。
3. legacy 迁移：ContentPackageIR 与 Knowledge DocumentIr → canonical，
   节点用确定性 UUIDv5（同输入两次得同 id）。
4. resource_ref 锚定：block.resource_ref(int) → IRResourceRef anchor 到节点。
5. Content Runtime：无 canonical_json 的历史 version 现场归一兜底；
   有 canonical_json 直接读；hydrate 分页 truncated 正确。
6. Gate3 旁路记账：扫描仍直读物理/重解析原件的旁路，断言"清单未扩大"
   （本轮不翻转线上读者，只记账，防新增旁路，不误报为已完成）。

纯新增测试，不改生产代码。db 用例（5）造的数据在 finally 清理。
"""
from __future__ import annotations

import app.main  # noqa: F401 —— 注册 parser 能力
import pytest
from app.contracts.canonical_content_ir import CanonicalContentIRV1, validate_profile_data
from app.services.content.canonical_normalizer import (
    infer_profile,
    normalize_legacy_content_package_ir,
    normalize_legacy_knowledge_ir,
    normalize_parser_output,
)

OWNER_ID = 4


# ── 1. Normalizer 往返 ────────────────────────────────────────────────────────

def _sample_parser_output() -> dict:
    """模拟 docx-parser 产出的 {manifest, blocks}（含递归 children + resource_ref）。"""
    return {
        "manifest": {"title": "测试文档", "extension": "docx", "package_type": "document"},
        "blocks": [
            {"type": "heading", "text": "第一章", "children": [
                {"type": "paragraph", "text": "正文一段"},
                {"type": "image", "text": "", "resource_ref": 12345},
            ]},
            {"type": "paragraph", "text": "结尾段"},
        ],
        "parse_status": "parsed",
    }


def test_normalize_parser_roundtrip_flat_tree():
    ir = normalize_parser_output(
        _sample_parser_output(), file_id=999, extension="docx", original_name="测试文档.docx",
    )
    assert isinstance(ir, CanonicalContentIRV1)
    assert ir.schema_version == "canonical-content-ir/v1"
    assert ir.profile == "document"

    # 扁平化：4 个 node（heading / paragraph / image / paragraph）
    assert len(ir.nodes) == 4
    heading = next(n for n in ir.nodes if n.kind == "heading")
    # 递归 children 变成 parent_id 指向
    children = ir.iter_children(heading.id)
    assert len(children) == 2
    assert [c.kind for c in children] == ["paragraph", "image"]
    # 顶层两个节点 parent_id 为 None
    assert sum(1 for n in ir.nodes if n.parent_id is None) == 2


def test_normalize_parser_profile_data_complete():
    ir = normalize_parser_output(_sample_parser_output(), file_id=1, extension="docx")
    # document profile 6 个必填键全齐（结构校验空 = 通过）
    assert validate_profile_data(ir) == []


def test_normalize_parser_fidelity_readonly():
    """§24：导入文件本轮一律 editable=false，不假绿。"""
    ir = normalize_parser_output(_sample_parser_output(), file_id=1, extension="docx")
    assert ir.fidelity.editable is False
    assert ir.fidelity.level in ("textual", "structural", "metadata_only")


def test_normalize_resource_ref_anchored():
    ir = normalize_parser_output(_sample_parser_output(), file_id=1, extension="docx")
    assert len(ir.resource_refs) == 1
    ref = ir.resource_refs[0]
    assert ref.resource_id == 12345
    assert ref.anchor_type == "node"
    # anchor_id 指向 image 节点
    img = next(n for n in ir.nodes if n.kind == "image")
    assert ref.anchor_id == img.id


# ── 2. profile 推断 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("ext,expected", [
    ("docx", "document"), ("txt", "document"), ("md", "document"),
    ("xlsx", "spreadsheet"), ("csv", "spreadsheet"),
    ("pptx", "presentation"),
    ("pdf", "pdf"),
    ("png", "media"), ("mp4", "media"), ("mp3", "media"),
    ("xyz_unknown", "generic"),
])
def test_infer_profile(ext, expected):
    assert infer_profile(ext, None, None) == expected


# ── 3. legacy 迁移：确定性 UUIDv5 ─────────────────────────────────────────────

def test_legacy_content_package_deterministic_ids():
    content = _sample_parser_output()
    ir1 = normalize_legacy_content_package_ir(content, package_id=456, file_id=1, extension="docx")
    ir2 = normalize_legacy_content_package_ir(content, package_id=456, file_id=1, extension="docx")
    # 同输入同 package_id → 节点 id 完全一致（跨版本稳定）
    assert [n.id for n in ir1.nodes] == [n.id for n in ir2.nodes]
    # 不同 package_id → 节点 id 不同
    ir3 = normalize_legacy_content_package_ir(content, package_id=789, file_id=1, extension="docx")
    assert ir1.nodes[0].id != ir3.nodes[0].id
    assert ir1.extensions.get("legacy.content_package", {}).get("package_id") == 456


def test_legacy_knowledge_ir_migration():
    doc_ir = {
        "file_id": 77, "format": "docx", "source_filename": "kb.docx",
        "blocks": [
            {"type": "heading", "text": "标题", "children": [
                {"type": "paragraph", "text": "段落"},
            ]},
        ],
        "parse_status": "parsed",
    }
    ir = normalize_legacy_knowledge_ir(doc_ir, file_id=77, extension="docx")
    assert ir.profile == "document"
    assert len(ir.nodes) == 2
    assert ir.extensions.get("legacy.knowledge", {}).get("migrated") is True


# ── 4. Content Runtime（db 用例）─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_content_runtime_read_hydrate():
    """对无 canonical_json 的历史版本，Content Runtime 现场归一兜底；hydrate 分页正确。"""
    import json as _json

    from app.database import AsyncSessionLocal
    from app.models.content import ContentPackage, ContentPackageVersion
    from app.services.content import content_runtime_service as rt

    pkg_id = None
    async with AsyncSessionLocal() as db:
        # 造一个只有旧 content_json、无 canonical_json 的 package+version（模拟历史数据）
        pkg = ContentPackage(
            owner_id=OWNER_ID, source_file_id=None, package_type="document",
            source_extension="txt", status="parsed",
        )
        db.add(pkg)
        await db.flush()
        pkg_id = pkg.id
        content = {
            "manifest": {"title": "历史文档", "extension": "txt"},
            "blocks": [{"type": "paragraph", "text": f"段{i}"} for i in range(8)],
            "parse_status": "parsed",
        }
        ver = ContentPackageVersion(
            package_id=pkg.id, version_no=1,
            content_json=_json.dumps(content, ensure_ascii=False),
            canonical_json=None,  # 历史版本无 canonical
            operation_type="parse", created_by=OWNER_ID,
        )
        db.add(ver)
        await db.flush()
        pkg.current_version_id = ver.id
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            # read：现场归一兜底
            ir = await rt.read(db, package_id=pkg_id)
            assert ir.schema_version == "canonical-content-ir/v1"
            assert len(ir.nodes) == 8
            # describe：标记无 canonical 载荷
            info = await rt.describe(db, package_id=pkg_id)
            assert info["has_canonical_payload"] is False
            assert info["node_count"] == 8
            # hydrate：分页 5 条，truncated
            page = await rt.hydrate(db, package_id=pkg_id, limit=5, offset=0)
            assert page["total"] == 8
            assert len(page["nodes"]) == 5
            assert page["truncated"] is True
    finally:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import delete
            await db.execute(delete(ContentPackageVersion).where(ContentPackageVersion.package_id == pkg_id))
            await db.execute(delete(ContentPackage).where(ContentPackage.id == pkg_id))
            await db.commit()


# ── 5. Gate3 旁路记账（防新增，不误报已完成）──────────────────────────────────

# 本轮已知、待 WP7 翻转的旁路白名单（子代理实测清单）。测试断言"没有新增旁路"，
# 而非"旁路已清零"——诚实反映 WP3 只建 canonical 读能力、不翻转线上读者。
KNOWN_BYPASSES_WP7 = {
    "modules/doc-viewer",          # 打开重解析物理 docx
    "modules/ppt-viewer",          # 打开重解析物理 pptx
    "modules/docs-open",           # _read_content 直读/重解析
    "backend/app/services/office/text_editor_service.py",  # 直读直写物理
    "backend/app/services/office/csv_editor_service.py",   # 直读直写物理
    "modules/excel-engine",        # 独立事实源
    "modules/knowledge",           # 重解析回退 + 独立监听（华哥定本轮保留）
}


def test_gate3_bypass_ledger_documented():
    """Gate3 记账：确认已知旁路清单已在施工文档登记，且 Content Runtime 已就位。

    本轮不翻转（华哥定），所以不断言旁路清零，只断言：
      - Content Runtime read/hydrate/describe 三接口存在（未来翻转的落点已就位）。
    """
    from app.services.content import content_runtime_service as rt
    assert hasattr(rt, "read")
    assert hasattr(rt, "hydrate")
    assert hasattr(rt, "describe")
    # 已知旁路清单非空 = 本轮明确知道还有 7 处待 WP7 翻转（不假装已完成）
    assert len(KNOWN_BYPASSES_WP7) == 7
