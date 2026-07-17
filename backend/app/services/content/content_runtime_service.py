"""Content Runtime —— 统一内容读入口（正式路径）。

只读服务。read/hydrate 返回 CanonicalContentIRV1:
  - Version 有 canonical_json → 直接反序列化
  - 无 canonical_json → 现场把 content_json 归一成 canonical（不落库）

写路径见 office_workspace_service / package_service / export_service。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.canonical_content_ir import CanonicalContentIRV1, IRNode
from app.models.content import ContentPackage, ContentPackageVersion
from app.services.content.canonical_normalizer import (
    infer_profile,
    normalize_legacy_content_package_ir,
)

logger = logging.getLogger("v2.content").getChild("runtime")


class ContentRuntimeError(Exception):
    """内容运行时错误(package/version 缺失、内容不可读等)。"""


async def _resolve_version(
    db: AsyncSession, *, package_id: int | None, version_id: int | None,
) -> tuple[ContentPackage, ContentPackageVersion]:
    """定位 (package, version)。version_id 优先;否则取 package 的 current/最新版。"""
    if version_id is not None:
        ver = await db.get(ContentPackageVersion, version_id)
        if ver is None:
            raise ContentRuntimeError(f"version {version_id} not found")
        pkg = await db.get(ContentPackage, ver.package_id)
        if pkg is None or pkg.deleted:
            raise ContentRuntimeError(f"package {ver.package_id} not found")
        return pkg, ver

    if package_id is None:
        raise ContentRuntimeError("package_id or version_id required")
    pkg = await db.get(ContentPackage, package_id)
    if pkg is None or pkg.deleted:
        raise ContentRuntimeError(f"package {package_id} not found")
    ver: ContentPackageVersion | None = None
    if pkg.current_version_id:
        ver = await db.get(ContentPackageVersion, pkg.current_version_id)
    if ver is None:
        ver = await db.scalar(
            select(ContentPackageVersion)
            .where(ContentPackageVersion.package_id == package_id)
            .order_by(ContentPackageVersion.version_no.desc())
            .limit(1)
        )
    if ver is None:
        raise ContentRuntimeError(f"package {package_id} has no version")
    return pkg, ver


def _canonical_from_version(pkg: ContentPackage, ver: ContentPackageVersion) -> CanonicalContentIRV1:
    """从 version 取 CanonicalContentIRV1:有 canonical_json 读它,否则现场归一旧 content_json。"""
    if ver.canonical_json:
        try:
            return CanonicalContentIRV1.model_validate_json(ver.canonical_json)
        except Exception as exc:  # canonical_json 损坏 → 降级到旧 content_json 归一
            logger.warning("canonical_json parse failed pkg=%s ver=%s: %s", pkg.id, ver.id, exc)

    # 兜底:历史版本无 canonical_json,现场把旧 content_json 归一(不落库,只服务本次读)。
    try:
        content = json.loads(ver.content_json) if ver.content_json else {"manifest": {}, "blocks": []}
    except (json.JSONDecodeError, TypeError):
        content = {"manifest": {}, "blocks": []}
    ext = (pkg.source_extension or "").lower().lstrip(".")
    return normalize_legacy_content_package_ir(
        content, package_id=pkg.id, file_id=pkg.source_file_id, extension=ext,
    )


async def read(
    db: AsyncSession, *, package_id: int | None = None, version_id: int | None = None,
) -> CanonicalContentIRV1:
    """读整份 CanonicalContentIRV1。大文件也全量返回(分片按需请用 hydrate)。"""
    pkg, ver = await _resolve_version(db, package_id=package_id, version_id=version_id)
    return _canonical_from_version(pkg, ver)


async def read_dict(
    db: AsyncSession, *, package_id: int | None = None, version_id: int | None = None,
) -> dict[str, Any]:
    """read 的 dict 形态(供 capability/HTTP 层直接 JSON 序列化)。"""
    ir = await read(db, package_id=package_id, version_id=version_id)
    return ir.model_dump(mode="json")


async def hydrate(
    db: AsyncSession, *,
    package_id: int | None = None, version_id: int | None = None,
    page: int | None = None, slide: int | None = None,
    sheet: str | None = None, anchor_id: str | None = None,
    limit: int = 500, offset: int = 0,
) -> dict[str, Any]:
    """按定位/分页拉一片 nodes(大文件按需加载,不整份塞前端)。

    返回 {profile, total, offset, limit, nodes[], resource_refs[], truncated}。
    定位优先级:anchor_id(子树) > page/slide/sheet(该页节点) > 全量分页。
    """
    pkg, ver = await _resolve_version(db, package_id=package_id, version_id=version_id)
    ir = _canonical_from_version(pkg, ver)

    nodes = ir.nodes
    if anchor_id is not None:
        nodes = _subtree(ir, anchor_id)
    elif page is not None:
        nodes = [n for n in ir.nodes if n.attrs.get("page") == page]
    elif slide is not None:
        nodes = [n for n in ir.nodes if n.attrs.get("slide") == slide or n.attrs.get("page") == slide]
    elif sheet is not None:
        nodes = [n for n in ir.nodes if str(n.attrs.get("sheet") or "") == sheet or n.text == sheet]

    total = len(nodes)
    window = nodes[offset:offset + limit]
    node_ids = {n.id for n in window}
    refs = [r for r in ir.resource_refs if r.anchor_id in node_ids or r.anchor_type == "document"]
    return {
        "profile": ir.profile,
        "schema_version": ir.schema_version,
        "total": total,
        "offset": offset,
        "limit": limit,
        "truncated": offset + limit < total,
        "nodes": [n.model_dump(mode="json") for n in window],
        "resource_refs": [r.model_dump(mode="json") for r in refs],
        "fidelity": ir.fidelity.model_dump(mode="json"),
    }


def _subtree(ir: CanonicalContentIRV1, root_id: str) -> list[IRNode]:
    """取 root_id 及其所有后代(DFS,按 order)。"""
    by_parent: dict[str | None, list[IRNode]] = {}
    for n in ir.nodes:
        by_parent.setdefault(n.parent_id, []).append(n)
    for children in by_parent.values():
        children.sort(key=lambda n: n.order)

    out: list[IRNode] = []
    root = next((n for n in ir.nodes if n.id == root_id), None)
    if root is None:
        return out

    def _walk(node: IRNode) -> None:
        out.append(node)
        for child in by_parent.get(node.id, []):
            _walk(child)

    _walk(root)
    return out


async def describe(
    db: AsyncSession, *, package_id: int | None = None, version_id: int | None = None,
) -> dict[str, Any]:
    """轻量元信息(不拉 nodes 正文):profile/fidelity/node 计数/资源计数/处理状态。

    供前端处理中状态展示与 Resolver 判定,避免整份读。
    """
    pkg, ver = await _resolve_version(db, package_id=package_id, version_id=version_id)
    ir = _canonical_from_version(pkg, ver)
    _ = infer_profile  # 已在归一里推断,这里直接用 ir.profile
    return {
        "package_id": pkg.id,
        "version_id": ver.id,
        "version_no": ver.version_no,
        "profile": ir.profile,
        "schema_version": ir.schema_version,
        "package_status": pkg.status,
        "fidelity": ir.fidelity.model_dump(mode="json"),
        "node_count": len(ir.nodes),
        "resource_ref_count": len(ir.resource_refs),
        "has_canonical_payload": bool(ver.canonical_json),
        "diagnostics": [d.model_dump(mode="json") for d in ir.diagnostics],
    }
