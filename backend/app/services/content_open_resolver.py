"""Content Open Resolver —— 每个文件只给一个 Product/Adapter/Mode 结论。

解析顺序（§19.5 冻结，不得改）：
  定位 File/Revision/Artifact Projection
  → 权限
  → Package/Version
  → Ingestion/readable state
  → Product 权限
  → FileAssociation
  → Adapter/fidelity
  → 模式降级
  → 编辑租约

本轮（WP4）：建真 Resolver + 真实数据读路径；不翻转线上 Viewer/Editor 旁路（WP7）。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from app.models.content import ContentPackage
from app.models.content_runtime import ContentEditLease, IngestionRun
from app.models.file import File
from app.models.user import User
from app.schemas.product import OpenContentIntentV1
from app.services.content import content_runtime_service
from app.services.file_share_service import check_file_access
from app.services.product_catalog_service import (
    find_associations_for_extension,
    get_effective_product,
    list_effective_products,
)

logger = logging.getLogger("v2.product").getChild("resolver")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def _locate_file(db: AsyncSession, file_id: int) -> File:
    file = await db.get(File, file_id)
    if file is None or getattr(file, "deleted", False):
        raise NotFound(f"File {file_id} not found")
    return file


async def _locate_package(
    db: AsyncSession, *, file_id: int | None, package_id: int | None,
) -> ContentPackage | None:
    if package_id is not None:
        pkg = await db.get(ContentPackage, package_id)
        if pkg is None or pkg.deleted:
            raise NotFound(f"Package {package_id} not found")
        return pkg
    if file_id is None:
        return None
    return await db.scalar(
        select(ContentPackage).where(
            ContentPackage.source_file_id == file_id,
            ContentPackage.deleted.is_(False),
        ).order_by(ContentPackage.id.desc()).limit(1)
    )


async def _latest_ingestion(db: AsyncSession, file_id: int | None) -> dict[str, Any] | None:
    if file_id is None:
        return None
    run = await db.scalar(
        select(IngestionRun)
        .where(IngestionRun.file_id == file_id)
        .order_by(IngestionRun.created_at.desc())
        .limit(1)
    )
    if run is None:
        return None
    return {
        "runId": run.id,
        "status": run.status,
        "errorCode": run.error_code,
        "packageId": run.package_id,
        "packageVersionId": run.package_version_id,
        "generation": run.generation,
    }


async def _active_lease(db: AsyncSession, package_id: int | None) -> dict[str, Any] | None:
    if package_id is None:
        return None
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    lease = await db.scalar(
        select(ContentEditLease)
        .where(
            ContentEditLease.package_id == package_id,
            ContentEditLease.expires_at > now,
        )
        .order_by(ContentEditLease.id.desc())
        .limit(1)
    )
    if lease is None:
        return None
    return {
        "holderId": lease.holder_id,
        "expiresAt": lease.expires_at.isoformat() if lease.expires_at else None,
        "baseVersionId": lease.base_version_id,
        "revision": lease.revision,
        # 不回传 token_hash
    }


def _pick_association(
    candidates: list[dict[str, Any]],
    *,
    preferred_product_id: str | None,
    allowed_product_ids: set[str],
) -> dict[str, Any] | None:
    filtered = [c for c in candidates if c.get("productId") in allowed_product_ids]
    if preferred_product_id:
        preferred = [c for c in filtered if c.get("productId") == preferred_product_id]
        if preferred:
            return preferred[0]
    return filtered[0] if filtered else None


def _grant_mode(
    requested: str,
    association: dict[str, Any],
    *,
    fidelity_editable: bool,
    user_can_edit: bool,
    extension: str,
) -> tuple[str, str | None]:
    """模式降级：edit 请求可能落到 view。"""
    modes = [str(m) for m in (association.get("modes") or ["view"])]
    readonly_formats = {str(x).lower().lstrip(".") for x in (association.get("readOnlyFormats") or [])}
    ext = (extension or "").lower().lstrip(".")

    if requested == "edit":
        if "edit" not in modes:
            return "view", "PRODUCT_MODE_UNSUPPORTED"
        if ext in readonly_formats:
            return "view", "FORMAT_READONLY"
        if not fidelity_editable:
            return "view", "FIDELITY_READONLY"
        if not user_can_edit:
            return "view", "PERMISSION_READONLY"
        return "edit", None
    return "view", None


async def resolve_open_content(
    db: AsyncSession,
    user: User,
    intent: OpenContentIntentV1,
) -> dict[str, Any]:
    resolution_id = _new_id("res")
    request_id = intent.requestId or _new_id("req")

    src = intent.source
    if not any([src.fileId, src.packageId, src.versionId, src.deepLink]):
        raise ValidationError("OpenContent source required (fileId|packageId|versionId|deepLink)")

    # 1) 定位 File / Package
    file: File | None = None
    file_id = src.fileId
    package = await _locate_package(db, file_id=file_id, package_id=src.packageId)

    if package is not None and file_id is None:
        file_id = package.source_file_id

    if file_id is not None:
        # 2) 权限
        access = await check_file_access(db, file_id, user.id)
        if not access.get("accessible"):
            raise PermissionDenied("No access to file")
        file = await _locate_file(db, file_id)
        if package is None:
            package = await _locate_package(db, file_id=file_id, package_id=None)

    extension = ""
    mime = "application/octet-stream"
    title = ""
    if file is not None:
        extension = (file.extension or "").lower().lstrip(".")
        mime = file.mime_type or mime
        title = file.name or ""
    elif package is not None:
        extension = (package.source_extension or "").lower().lstrip(".")
        title = f"package-{package.id}"

    # 3) Package/Version + readable state（复用 WP3 describe）
    content_meta: dict[str, Any] | None = None
    fidelity_editable = False
    version_id = src.versionId
    if package is not None:
        try:
            content_meta = await content_runtime_service.describe(
                db,
                package_id=package.id,
                version_id=version_id or package.current_version_id,
            )
            version_id = content_meta.get("version_id") or version_id
            fidelity = content_meta.get("fidelity") or {}
            fidelity_editable = bool(fidelity.get("editable"))
        except Exception as exc:
            logger.info("content describe skip package=%s: %s", package.id, exc)
            content_meta = {
                "package_id": package.id,
                "version_id": package.current_version_id,
                "package_status": package.status,
                "has_canonical_payload": False,
                "fidelity": {"editable": False, "level": "unknown"},
            }

    # 4) Ingestion
    ingestion = await _latest_ingestion(db, file_id)

    # 5) Product 权限 + 6) FileAssociation
    catalog = await list_effective_products(db, user)
    allowed_ids = {str(p["productId"]) for p in catalog["items"]}
    candidates = find_associations_for_extension(extension)
    # deepLink 优先走 preferred / scheme
    if src.deepLink and not candidates:
        # deepLink 无文件时仍可落到 preferred product
        pass

    picked = _pick_association(
        candidates,
        preferred_product_id=intent.preferredProductId,
        allowed_product_ids=allowed_ids,
    )

    if picked is None and intent.preferredProductId and intent.preferredProductId in allowed_ids:
        # 无关联但仍指定 product（如 AI/知识库打开工作区）
        product = await get_effective_product(db, user, intent.preferredProductId)
        association = {
            "associationId": f"{intent.preferredProductId}.workspace",
            "modes": ["view"],
            "adapterId": f"{intent.preferredProductId}.workspace",
            "priority": 0,
            "readOnlyFormats": [],
        }
        product_id = intent.preferredProductId
    elif picked is None:
        return {
            "resolutionId": resolution_id,
            "requestId": request_id,
            "resolverVersion": intent.resolverVersion or "v1",
            "outcome": "unsupported",
            "productId": None,
            "adapterId": None,
            "grantedMode": "view",
            "readonlyReason": "NO_PRODUCT_ASSOCIATION",
            "file": _file_payload(file),
            "package": _package_payload(package),
            "version": content_meta,
            "ingestion": ingestion,
            "catalogRevision": catalog.get("catalogRevision"),
            "session": None,
        }
    else:
        product_id = str(picked["productId"])
        association = picked["association"]
        product = await get_effective_product(db, user, product_id)

    if product is None:
        raise PermissionDenied(f"Product {product_id} not available")

    # 7) Adapter/fidelity + 8) 模式降级
    user_can_edit = (getattr(user, "role", None) or "viewer") in {"editor", "admin"}
    granted_mode, readonly_reason = _grant_mode(
        intent.requestedMode,
        association,
        fidelity_editable=fidelity_editable,
        user_can_edit=user_can_edit,
        extension=extension,
    )

    # 9) 编辑租约（只读时不强制持有）
    lease = await _active_lease(db, package.id if package else None)
    if granted_mode == "edit" and lease and lease.get("holderId") not in (None, user.id):
        granted_mode = "view"
        readonly_reason = "LEASE_HELD_BY_OTHER"

    session = {
        "sessionId": _new_id("ds"),
        "productId": product_id,
        "packageId": package.id if package else None,
        "versionId": version_id,
        "fileId": file_id,
        "title": title or product.get("displayName"),
        "contentType": (content_meta or {}).get("profile") or package.package_type if package else "generic",
        "format": extension,
        "adapterId": association.get("adapterId"),
        "requestedMode": intent.requestedMode,
        "grantedMode": granted_mode,
        "lifecycle": "open",
        "dirty": False,
        "expectedVersionId": version_id,
        "activation": intent.activation,
    }

    return {
        "resolutionId": resolution_id,
        "requestId": request_id,
        "resolverVersion": intent.resolverVersion or "v1",
        "outcome": "resolved",
        "productId": product_id,
        "adapterId": association.get("adapterId"),
        "associationId": association.get("associationId"),
        "grantedMode": granted_mode,
        "readonlyReason": readonly_reason,
        "product": {
            "productId": product.get("productId"),
            "displayName": product.get("displayName"),
            "entryComponentKey": product.get("entryComponentKey"),
            "workspaceKind": product.get("workspaceKind"),
            "windowPolicy": product.get("windowPolicy"),
        },
        "file": _file_payload(file),
        "package": _package_payload(package),
        "version": content_meta,
        "contentType": (content_meta or {}).get("profile"),
        "format": extension,
        "mime": mime,
        "title": title,
        "permissions": {
            "canView": True,
            "canEdit": granted_mode == "edit",
            "role": getattr(user, "role", None),
        },
        "ingestion": ingestion,
        "lock": lease,
        "session": session,
        "catalogRevision": catalog.get("catalogRevision"),
        "activation": intent.activation,
    }


def _file_payload(file: File | None) -> dict[str, Any] | None:
    if file is None:
        return None
    return {
        "fileId": file.id,
        "name": file.name,
        "extension": file.extension,
        "mimeType": file.mime_type,
        "size": file.size,
        "currentRevisionId": getattr(file, "current_revision_id", None),
    }


def _package_payload(package: ContentPackage | None) -> dict[str, Any] | None:
    if package is None:
        return None
    return {
        "packageId": package.id,
        "status": package.status,
        "packageType": package.package_type,
        "profile": package.profile,
        "currentVersionId": package.current_version_id,
        "sourceFileId": package.source_file_id,
        "sourceRevisionId": package.source_revision_id,
        "activeIngestionId": package.active_ingestion_id,
    }
