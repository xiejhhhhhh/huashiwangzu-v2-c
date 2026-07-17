"""Office workspace / Content Runtime 写骨架（WP5）。

铁律（§19.6）：
- Adapter 只能调 Content Runtime，不接物理路径、不自己调 Parser。
- createDraft：原子建 source-less Package + 空白 Version，file_id=null。
- autosave：只新增 Canonical Version，不产生桌面 File。
- 首次显式 Save / Save As：本轮骨架返回 deferred 指引（物化 File/projection 完整链路 WP7/后续）。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.canonical_content_ir import CanonicalContentIRV1, IRFidelity, IRNode
from app.contracts.content_hash import content_sha256
from app.contracts.ids import new_uuid7
from app.core.exceptions import ConflictError, NotFound, PermissionDenied, ValidationError
from app.models.content import ContentPackage, ContentPackageVersion
from app.services.content import content_runtime_service
from app.services.content.canonical_normalizer import normalize_parser_output
from app.services.content_edit_lease_service import assert_lease

logger = logging.getLogger("v2.product").getChild("office")


def _blank_canonical(*, title: str, extension: str, profile: str) -> CanonicalContentIRV1:
    root_id = new_uuid7()
    node = IRNode(
        id=root_id,
        kind="document",
        order=0,
        parent_id=None,
        text=title or "未命名文档",
        attrs={"title": title or "未命名文档"},
    )
    # 用 normalizer 走一遍，确保 profile_data 必填键骨架齐全。
    raw = {
        "manifest": {
            "title": title or "未命名文档",
            "extension": extension,
            "package_type": profile,
            "created_by_parser": "office:createDraft",
        },
        "blocks": [
            {
                "id": root_id,
                "type": "paragraph",
                "text": "",
                "children": [],
            }
        ],
        "parse_status": "draft",
    }
    try:
        return normalize_parser_output(
            raw,
            file_id=None,
            extension=extension,
            original_name=title or "untitled",
            size=0,
        )
    except Exception:
        return CanonicalContentIRV1(
            schema_version="canonical-content-ir/v1",
            profile=profile,  # type: ignore[arg-type]
            nodes=[node],
            resource_refs=[],
            profile_data={},
            fidelity=IRFidelity(level="structural", editable=True),
            diagnostics=[],
        )


def _profile_for_extension(extension: str) -> str:
    ext = (extension or "").lower().lstrip(".")
    if ext in {"xlsx", "xls", "csv"}:
        return "spreadsheet"
    if ext in {"pptx", "ppt"}:
        return "presentation"
    if ext == "pdf":
        return "pdf"
    if ext in {"png", "jpg", "jpeg", "gif", "webp", "mp3", "mp4"}:
        return "media"
    if ext in {"txt", "md", "json", "log"}:
        return "document"
    return "document"


async def create_draft(
    db: AsyncSession,
    *,
    owner_id: int,
    product_id: str = "office",
    content_type: str = "document",
    extension: str = "docx",
    title: str = "未命名文档",
    adapter_id: str | None = None,
) -> dict[str, Any]:
    ext = (extension or "docx").lower().lstrip(".")
    profile = _profile_for_extension(ext) if content_type == "document" else (
        content_type if content_type in {
            "document", "spreadsheet", "presentation", "pdf", "media", "generic",
        } else "document"
    )
    canonical = _blank_canonical(title=title, extension=ext, profile=profile)
    # createDraft 是空白新建，不是导入文件：允许编辑（§19.6）。
    # WP3 normalizer 对导入文件一律 editable=false；草稿必须显式放开，否则 Resolver 会 FIDELITY_READONLY。
    canonical.fidelity.editable = True
    if canonical.fidelity.level == "metadata_only":
        canonical.fidelity.level = "structural"
    if "edit" not in (canonical.fidelity.supported_features or []):
        canonical.fidelity.supported_features = list(
            dict.fromkeys([*(canonical.fidelity.supported_features or []), "edit", "read"])
        )
    canonical_json = canonical.model_dump_json()
    # 旧 content_json 兼容形状（线上读者 WP7 前仍可能读到它）
    content_ir = {
        "manifest": {
            "title": title,
            "extension": ext,
            "package_type": profile,
            "created_by_parser": "office:createDraft",
            "product_id": product_id,
            "adapter_id": adapter_id or f"{product_id}.document",
        },
        "blocks": [],
        "parse_status": "draft",
    }

    pkg = ContentPackage(
        owner_id=owner_id,
        source_file_id=None,
        package_type=profile,
        origin_type="generated",
        source_extension=ext,
        package_version="1.0",
        status="parsed",
        profile=profile,
        schema_version="canonical-content-ir/v1",
        manifest_json=json.dumps(content_ir["manifest"], ensure_ascii=False),
    )
    db.add(pkg)
    await db.flush()

    version = ContentPackageVersion(
        package_id=pkg.id,
        version_no=1,
        content_json=json.dumps(content_ir, ensure_ascii=False),
        canonical_json=canonical_json,
        schema_version="canonical-content-ir/v1",
        profile=profile,
        content_sha256=content_sha256(canonical),
        source_sha256=None,
        fidelity_level=canonical.fidelity.level if canonical.fidelity else "structural",
        summary=f"draft:{title}",
        operation_type="create_draft",
        created_by=owner_id,
    )
    db.add(version)
    await db.flush()
    pkg.current_version_id = version.id
    await db.commit()
    await db.refresh(pkg)
    await db.refresh(version)

    return {
        "packageId": pkg.id,
        "versionId": version.id,
        "versionNo": version.version_no,
        "fileId": None,
        "productId": product_id,
        "adapterId": adapter_id or f"{product_id}.document",
        "title": title,
        "extension": ext,
        "profile": profile,
        "status": pkg.status,
        "contentSha256": version.content_sha256,
        "grantedMode": "edit",
    }


async def read_package(
    db: AsyncSession, *, package_id: int, version_id: int | None, owner_id: int,
) -> dict[str, Any]:
    pkg = await db.get(ContentPackage, package_id)
    if pkg is None or pkg.deleted:
        raise NotFound(f"Package {package_id} not found")
    if pkg.owner_id != owner_id:
        # 本轮骨架只做 owner 隔离；共享权限走 WP5/后续 ContentAccessPolicyService
        raise PermissionDenied("Package access denied")
    ir = await content_runtime_service.read_dict(
        db, package_id=package_id, version_id=version_id,
    )
    meta = await content_runtime_service.describe(
        db, package_id=package_id, version_id=version_id,
    )
    return {"package": meta, "content": ir}


async def hydrate_package(
    db: AsyncSession,
    *,
    package_id: int,
    owner_id: int,
    version_id: int | None = None,
    page: int | None = None,
    slide: int | None = None,
    sheet: str | None = None,
    anchor_id: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    pkg = await db.get(ContentPackage, package_id)
    if pkg is None or pkg.deleted:
        raise NotFound(f"Package {package_id} not found")
    if pkg.owner_id != owner_id:
        raise PermissionDenied("Package access denied")
    return await content_runtime_service.hydrate(
        db,
        package_id=package_id,
        version_id=version_id,
        page=page,
        slide=slide,
        sheet=sheet,
        anchor_id=anchor_id,
        limit=limit,
        offset=offset,
    )


async def save_package(
    db: AsyncSession,
    *,
    package_id: int,
    owner_id: int,
    expected_version_id: int | None,
    lock_token: str | None,
    content: dict[str, Any] | None,
    summary: str | None = None,
    autosave: bool = True,
) -> dict[str, Any]:
    pkg = await db.get(ContentPackage, package_id)
    if pkg is None or pkg.deleted:
        raise NotFound(f"Package {package_id} not found")
    if pkg.owner_id != owner_id:
        raise PermissionDenied("Package access denied")

    await assert_lease(db, package_id=package_id, holder_id=owner_id, token=lock_token)

    if expected_version_id is not None and pkg.current_version_id != expected_version_id:
        raise ConflictError(
            f"Version conflict: expected {expected_version_id}, current {pkg.current_version_id}"
        )

    # content 缺省时复制当前 version 作为 no-op 快照（幂等友好）
    current = None
    if pkg.current_version_id:
        current = await db.get(ContentPackageVersion, pkg.current_version_id)

    if content is None:
        if current is None:
            raise ValidationError("No content and no current version")
        content_json = current.content_json
        canonical_json = current.canonical_json
        profile = current.profile or pkg.profile or "document"
        try:
            if canonical_json:
                canonical = CanonicalContentIRV1.model_validate_json(canonical_json)
            else:
                raw = json.loads(content_json) if content_json else {"manifest": {}, "blocks": []}
                canonical = normalize_parser_output(
                    raw, file_id=pkg.source_file_id, extension=pkg.source_extension or "",
                )
                canonical_json = canonical.model_dump_json()
        except Exception as exc:
            raise ValidationError(f"Invalid current content: {exc}") from exc
    else:
        # 允许直接传 Canonical IR 或旧 {manifest,blocks}
        if "nodes" in content and "profile" in content:
            canonical = CanonicalContentIRV1.model_validate(content)
            canonical_json = canonical.model_dump_json()
            content_json = json.dumps({
                "manifest": {
                    "title": summary or f"package-{package_id}",
                    "package_type": canonical.profile,
                    "created_by_parser": "office:save",
                },
                "blocks": [],
                "parse_status": "edited",
                "canonical_ref": True,
            }, ensure_ascii=False)
            profile = canonical.profile
        else:
            content_json = json.dumps(content, ensure_ascii=False)
            canonical = normalize_parser_output(
                content, file_id=pkg.source_file_id, extension=pkg.source_extension or "",
            )
            canonical_json = canonical.model_dump_json()
            profile = canonical.profile

    version_no = 1
    if current is not None:
        version_no = int(current.version_no) + 1

    version = ContentPackageVersion(
        package_id=pkg.id,
        version_no=version_no,
        parent_version_id=current.id if current else None,
        content_json=content_json,
        canonical_json=canonical_json,
        schema_version="canonical-content-ir/v1",
        profile=profile,
        content_sha256=content_sha256(canonical),
        source_sha256=current.source_sha256 if current else None,
        fidelity_level=canonical.fidelity.level if canonical.fidelity else None,
        summary=summary or ("autosave" if autosave else "save"),
        operation_type="autosave" if autosave else "save",
        created_by=owner_id,
    )
    db.add(version)
    await db.flush()
    pkg.current_version_id = version.id
    pkg.profile = profile
    pkg.schema_version = "canonical-content-ir/v1"
    pkg.status = "parsed"
    await db.commit()
    await db.refresh(version)

    return {
        "packageId": pkg.id,
        "versionId": version.id,
        "versionNo": version.version_no,
        "expectedVersionId": version.id,
        "contentSha256": version.content_sha256,
        "autosave": autosave,
        "fileId": pkg.source_file_id,  # draft 仍为 null
        "materialized": False if autosave or pkg.source_file_id is None else True,
        "note": None if autosave else (
            "first explicit save materializes File/projection in later slice; version committed"
            if pkg.source_file_id is None else None
        ),
    }


async def office_home(db: AsyncSession, *, owner_id: int) -> dict[str, Any]:
    """Office 首页骨架：最近草稿/包。"""
    from sqlalchemy import select

    rows = (
        await db.execute(
            select(ContentPackage)
            .where(
                ContentPackage.owner_id == owner_id,
                ContentPackage.deleted.is_(False),
            )
            .order_by(ContentPackage.updated_at.desc())
            .limit(20)
        )
    ).scalars().all()
    recent = []
    for pkg in rows:
        recent.append({
            "packageId": pkg.id,
            "title": (pkg.manifest_json or "")[:80],
            "profile": pkg.profile or pkg.package_type,
            "status": pkg.status,
            "currentVersionId": pkg.current_version_id,
            "sourceFileId": pkg.source_file_id,
            "updatedAt": pkg.updated_at.isoformat() if pkg.updated_at else None,
        })
    return {
        "productId": "office",
        "recent": recent,
        "createDocumentTypes": [
            {"extension": "docx", "label": "Word 文档", "contentType": "document"},
            {"extension": "pptx", "label": "演示文稿", "contentType": "presentation"},
            {"extension": "xlsx", "label": "工作簿", "contentType": "spreadsheet"},
        ],
    }
