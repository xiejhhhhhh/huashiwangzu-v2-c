"""Content Open / Draft / Package Runtime / Locks（方案07 §20.4 冻结 API）。

  POST /api/content/open
  POST /api/content/drafts
  GET  /api/content/packages/{id}/versions/{version_id}
  GET  /api/content/packages/{id}/hydrate
  POST /api/content/packages/{id}/save
  POST /api/content/packages/{id}/save-as
  POST /api/content/packages/{id}/export
  POST /api/content/packages/{id}/publish
  POST /api/content/packages/{id}/locks
  POST /api/content/packages/{id}/locks/renew
  DELETE /api/content/packages/{id}/locks/{token}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.product import (
    ContentExportRequest,
    ContentLockRenewRequest,
    ContentLockRequest,
    ContentPublishRequest,
    ContentSaveAsRequest,
    ContentSaveRequest,
    CreateDraftRequest,
    OpenContentIntentV1,
)
from app.services import content_edit_lease_service as lease_svc
from app.services import office_workspace_service as office_svc
from app.services.content.export_service import ContentExportService
from app.services.content_access_policy import require_package_edit, require_package_view
from app.services.content_open_resolver import resolve_open_content

router = APIRouter(prefix="/api/content", tags=["content-open"])


@router.post("/open")
async def open_content(
    intent: OpenContentIntentV1,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await resolve_open_content(db, user, intent)
    return ApiResponse(data=result)


@router.post("/drafts")
async def create_draft(
    body: CreateDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await office_svc.create_draft(
        db,
        owner_id=user.id,
        product_id=body.productId,
        content_type=body.contentType,
        extension=body.extension,
        title=body.title,
        adapter_id=body.adapterId,
    )
    return ApiResponse(data=result)


@router.get("/packages/{package_id}/versions/{version_id}")
async def get_package_version(
    package_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await require_package_view(db, package_id=package_id, user=user)
    result = await office_svc.read_package(
        db, package_id=package_id, version_id=version_id, owner_id=user.id,
    )
    return ApiResponse(data=result)


@router.get("/packages/{package_id}/hydrate")
async def hydrate_package(
    package_id: int,
    version_id: int | None = Query(default=None),
    page: int | None = Query(default=None),
    slide: int | None = Query(default=None),
    sheet: str | None = Query(default=None),
    anchor_id: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await require_package_view(db, package_id=package_id, user=user)
    result = await office_svc.hydrate_package(
        db,
        package_id=package_id,
        owner_id=user.id,
        version_id=version_id,
        page=page,
        slide=slide,
        sheet=sheet,
        anchor_id=anchor_id,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(data=result)


@router.post("/packages/{package_id}/save")
async def save_package(
    package_id: int,
    body: ContentSaveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    await require_package_edit(db, package_id=package_id, user=user)
    result = await office_svc.save_package(
        db,
        package_id=package_id,
        owner_id=user.id,
        expected_version_id=body.expectedVersionId,
        lock_token=body.lockToken,
        content=body.content,
        summary=body.summary,
        autosave=body.autosave,
    )
    return ApiResponse(data=result)


@router.post("/packages/{package_id}/save-as")
async def save_as_package(
    package_id: int,
    body: ContentSaveAsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    # 先提交内容版本，再声明 File 物化待后续切片（不假绿说已建 File）。
    if not body.title:
        raise ValidationError("title required")
    await require_package_edit(db, package_id=package_id, user=user)
    saved = await office_svc.save_package(
        db,
        package_id=package_id,
        owner_id=user.id,
        expected_version_id=body.expectedVersionId,
        lock_token=body.lockToken,
        content=body.content,
        summary=f"save-as:{body.title}",
        autosave=False,
    )
    return ApiResponse(data={
        **saved,
        "saveAs": {
            "title": body.title,
            "parentFolderId": body.parentFolderId,
            "materializedFile": False,
            "note": "Canonical version committed; File materialization via export/publish",
        },
    })




@router.post("/packages/{package_id}/export")
async def export_package(
    package_id: int,
    body: ContentExportRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """导出为物理文件（复用现有 ContentExportService）。"""
    await require_package_edit(db, package_id=package_id, user=user)
    fmt = (body.format if body else None) or None
    svc = ContentExportService()
    result = await svc.export(db, package_id, target_format=fmt, owner_id=user.id)
    return ApiResponse(data=result)


@router.post("/packages/{package_id}/publish")
async def publish_package(
    package_id: int,
    body: ContentPublishRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """发布投影/产物。完整物化策略沿用 export_service；正式发布路径。"""
    await require_package_edit(db, package_id=package_id, user=user)
    svc = ContentExportService()
    result = await svc.publish(
        db,
        package_id,
        target_file_id=(body.targetFileId if body else None),
        owner_id=user.id,
        conflict_policy=(body.conflictPolicy if body else "create_version") or "create_version",
    )
    return ApiResponse(data=result)

@router.post("/packages/{package_id}/locks")
async def acquire_lock(
    package_id: int,
    body: ContentLockRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await lease_svc.acquire_lease(
        db,
        package_id=package_id,
        holder_id=user.id,
        base_version_id=body.baseVersionId,
        ttl_seconds=body.ttlSeconds,
    )
    return ApiResponse(data=result)


@router.post("/packages/{package_id}/locks/renew")
async def renew_lock(
    package_id: int,
    body: ContentLockRenewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await lease_svc.renew_lease(
        db,
        package_id=package_id,
        holder_id=user.id,
        token=body.token,
        ttl_seconds=body.ttlSeconds,
    )
    return ApiResponse(data=result)


@router.delete("/packages/{package_id}/locks/{token}")
async def release_lock(
    package_id: int,
    token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await lease_svc.release_lease(
        db, package_id=package_id, holder_id=user.id, token=token,
    )
    return ApiResponse(data=result)
