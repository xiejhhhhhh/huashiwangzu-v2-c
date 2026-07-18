"""Product Catalog —— 只返回 Product，不返回 Parser/Provider/Service/Viewer/Editor。

合并顺序（§19.5 冻结）：
  ProductManifest → global override → user override
  → permission policy → capability availability → effective Product

覆盖层（framework_product_overrides）只能改 enabled/sort_order/visibility/允许的 config，
不能覆盖 productId/entryComponentKey/requiredCapabilities。
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_runtime import ProductOverride
from app.models.user import User
from app.schemas.product import ProductManifestV1

logger = logging.getLogger("v2.product").getChild("catalog")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_ROOT = PROJECT_ROOT / "products"

# 首批 10 个 Product（交付文档12固定）
FIRST_PARTY_PRODUCT_IDS = (
    "files", "office", "text", "media", "ai",
    "knowledge", "messages", "content-studio", "settings", "recycle",
)

_ROLE_RANK = {"viewer": 1, "editor": 2, "admin": 3}


def _role_ok(user_role: str, required: str) -> bool:
    return _ROLE_RANK.get(user_role or "viewer", 0) >= _ROLE_RANK.get(required or "viewer", 0)


def _load_raw_manifests(products_root: Path = PRODUCTS_ROOT) -> list[dict[str, Any]]:
    if not products_root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for product_dir in sorted(products_root.iterdir()):
        if not product_dir.is_dir() or product_dir.name.startswith(("_", ".")):
            continue
        path = product_dir / "product.json"
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Skip bad product manifest %s: %s", path, exc)
            continue
        # 校验合同形状；非法字段直接跳过，构建期 scan-products 会再拦一次。
        try:
            ProductManifestV1.model_validate(raw)
        except Exception as exc:
            logger.error("Invalid ProductManifestV1 %s: %s", path, exc)
            continue
        raw["_manifest_path"] = str(path)
        raw["_manifest_hash"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        rows.append(raw)
    return rows


def list_product_manifests(products_root: Path = PRODUCTS_ROOT) -> list[dict[str, Any]]:
    return _load_raw_manifests(products_root)


def get_product_manifest(product_id: str, products_root: Path = PRODUCTS_ROOT) -> dict[str, Any] | None:
    for m in _load_raw_manifests(products_root):
        if m.get("productId") == product_id:
            return m
    return None


async def _load_overrides(
    db: AsyncSession, *, user_id: int, product_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """返回 product_id → {global?, user?} 覆盖层。"""
    if not product_ids:
        return {}
    result = await db.execute(
        select(ProductOverride).where(
            ProductOverride.product_id.in_(product_ids),
            (
                ((ProductOverride.scope_type == "global") & (ProductOverride.scope_id == 0))
                | ((ProductOverride.scope_type == "user") & (ProductOverride.scope_id == user_id))
            ),
        )
    )
    out: dict[str, dict[str, Any]] = {}
    for row in result.scalars().all():
        bucket = out.setdefault(row.product_id, {})
        key = "user" if row.scope_type == "user" else "global"
        bucket[key] = {
            "enabled": bool(row.enabled),
            "sort_order": int(row.sort_order or 0),
            "visibility": _safe_json(row.visibility_json),
            "config": _safe_json(row.config_json),
            "revision": int(row.revision or 0),
        }
    return out


def _safe_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _permission_allows(manifest: dict[str, Any], user: User) -> bool:
    policy = manifest.get("permissionPolicy") or {}
    all_of = policy.get("allOf") or []
    any_of = policy.get("anyOf") or []
    role = getattr(user, "role", None) or "viewer"
    if all_of and not all(_role_ok(role, r) for r in all_of):
        return False
    if any_of and not any(_role_ok(role, r) for r in any_of):
        return False
    return True


def _apply_override(manifest: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return manifest
    # 身份/入口/requiredCapabilities 不可被覆盖。
    if "enabled" in override:
        manifest["enabled"] = bool(override["enabled"])
    if "sort_order" in override:
        manifest["sortOrder"] = int(override["sort_order"])
    if override.get("visibility"):
        base_vis = dict(manifest.get("visibility") or {})
        base_vis.update(override["visibility"])
        manifest["visibility"] = base_vis
    if override.get("config"):
        manifest["config"] = override["config"]
    return manifest


def _to_public(manifest: dict[str, Any], *, catalog_revision: str) -> dict[str, Any]:
    """前端可见字段。绝不下发 Parser/Provider 等非 Product 身份。"""
    icon_set = manifest.get("iconSet") or {}
    window_policy = manifest.get("windowPolicy") or {}
    ui_contract = manifest.get("uiContract")
    if not isinstance(ui_contract, dict):
        ui_contract = None
    return {
        "productId": manifest.get("productId"),
        "version": manifest.get("version"),
        "displayName": manifest.get("displayName"),
        "aliases": list(manifest.get("aliases") or []),
        "description": manifest.get("description") or "",
        "category": manifest.get("category") or "",
        "icon": icon_set.get("primary") or "Collection",
        "iconSet": icon_set,
        "entryComponentKey": manifest.get("entryComponentKey"),
        "workspaceKind": manifest.get("workspaceKind"),
        # App UI Kit contract — frontend only; backend never styles from this.
        "uiContract": ui_contract,
        "visibility": manifest.get("visibility") or {},
        "permissionPolicy": manifest.get("permissionPolicy") or {},
        "requiredCapabilities": list(manifest.get("requiredCapabilities") or []),
        "fileAssociations": list(manifest.get("fileAssociations") or []),
        "createDocumentTypes": list(manifest.get("createDocumentTypes") or []),
        "windowPolicy": window_policy,
        "activationPolicy": manifest.get("activationPolicy") or {},
        "deepLinks": list(manifest.get("deepLinks") or []),
        "commands": list(manifest.get("commands") or []),
        "frameworkCompatibility": manifest.get("frameworkCompatibility") or {},
        "legacyAppKeys": list(manifest.get("legacyAppKeys") or []),
        "enabled": bool(manifest.get("enabled", True)),
        "sortOrder": int(manifest.get("sortOrder") or window_policy.get("sortOrder") or 100),
        "defaultWidth": int(window_policy.get("defaultWidth") or 900),
        "defaultHeight": int(window_policy.get("defaultHeight") or 600),
        "singleton": bool(window_policy.get("singleton", True)),
        "allowMultiple": bool(window_policy.get("allowMultiple", False)),
        "manifestHash": manifest.get("_manifest_hash"),
        "catalogRevision": catalog_revision,
    }


async def list_effective_products(
    db: AsyncSession, user: User, *, products_root: Path = PRODUCTS_ROOT,
) -> dict[str, Any]:
    manifests = _load_raw_manifests(products_root)
    product_ids = [str(m.get("productId")) for m in manifests if m.get("productId")]
    overrides = await _load_overrides(db, user_id=user.id, product_ids=product_ids)

    # Catalog revision = 全部 manifest hash 的稳定摘要，前端可缓存失效。
    catalog_revision = hashlib.sha256(
        "|".join(sorted(m.get("_manifest_hash") or "" for m in manifests)).encode("utf-8")
    ).hexdigest()[:16]

    effective: list[dict[str, Any]] = []
    for m in manifests:
        pid = str(m.get("productId") or "")
        if not _permission_allows(m, user):
            continue
        ov = overrides.get(pid) or {}
        # global → user
        m = dict(m)
        m.setdefault("enabled", True)
        m = _apply_override(m, ov.get("global"))
        m = _apply_override(m, ov.get("user"))
        if not m.get("enabled", True):
            continue
        # capability availability：本轮骨架不查 runtime bus，缺 capability 记 diagnostics 但仍下发
        # （避免空 capability 列表把首批产品全滤掉）。真校验留后续。
        public = _to_public(m, catalog_revision=catalog_revision)
        effective.append(public)

    effective.sort(key=lambda x: (x.get("sortOrder") or 100, x.get("productId") or ""))
    return {
        "catalogRevision": catalog_revision,
        "count": len(effective),
        "items": effective,
        # Gate4：只返回 Product，不夹带 appKey/parser 列表
        "kind": "products",
    }


async def get_effective_product(
    db: AsyncSession, user: User, product_id: str, *, products_root: Path = PRODUCTS_ROOT,
) -> dict[str, Any] | None:
    catalog = await list_effective_products(db, user, products_root=products_root)
    for item in catalog["items"]:
        if item.get("productId") == product_id:
            return item
    return None


def find_associations_for_extension(
    extension: str, *, products_root: Path = PRODUCTS_ROOT,
) -> list[dict[str, Any]]:
    """按扩展名收集候选 FileAssociation（未做权限/覆盖过滤，Resolver 再筛）。"""
    ext = (extension or "").lower().lstrip(".")
    if not ext:
        return []
    candidates: list[dict[str, Any]] = []
    for m in _load_raw_manifests(products_root):
        for assoc in m.get("fileAssociations") or []:
            exts = [str(e).lower().lstrip(".") for e in (assoc.get("extensions") or [])]
            if ext in exts or "*" in exts:
                candidates.append({
                    "productId": m.get("productId"),
                    "product": m,
                    "association": assoc,
                    "priority": int(assoc.get("priority") or 0),
                })
    candidates.sort(key=lambda c: (-c["priority"], str(c["productId"])))
    return candidates
