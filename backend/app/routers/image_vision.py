from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.knowledge import Catalog
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.knowledge.catalog_service import CatalogService
from app.services.knowledge.pipeline import create_next_task, create_pipeline_tasks
from app.services.knowledge.vision import status_service

router = APIRouter(prefix="/api/image-vision", tags=["image-vision"])


class TriggerVisionRequest(BaseModel):
    catalog_id: int | None = None
    file_path: str | None = None
    owner_id: int | None = None


@router.post("/trigger")
async def trigger_extraction(
    body: TriggerVisionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    catalog = await _resolve_catalog(db, body, user.id)
    if catalog.channel_type not in status_service.VISION_CHANNELS:
        raise HTTPException(status_code=422, detail="Catalog is not a visual-capable file")
    await create_next_task(db, catalog.id, "extract")
    catalog.status = "pending"
    await db.commit()
    return ApiResponse(data={"catalogId": catalog.id, "status": "queued"})


@router.post("/dry-run")
async def batch_dry_run(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    return ApiResponse(data=await status_service.dry_run(db, limit=limit))


@router.get("/providers")
async def get_providers(user: User = Depends(require_permission("admin"))):
    return ApiResponse(data=await status_service.provider_status())


@router.get("/status/{catalog_id}")
async def get_status(
    catalog_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await status_service.catalog_status(db, catalog_id)
    if not data:
        raise HTTPException(status_code=404, detail="Knowledge file not found")
    return ApiResponse(data=data)


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    return ApiResponse(data=await status_service.extraction_stats(db))


async def _resolve_catalog(db: AsyncSession, body: TriggerVisionRequest, user_id: int) -> Catalog:
    if body.catalog_id:
        catalog = await db.get(Catalog, body.catalog_id)
        if not catalog:
            raise HTTPException(status_code=404, detail="Knowledge file not found")
        return catalog
    if body.file_path:
        catalog, is_new = await CatalogService.create_or_get(db, body.file_path, owner_id=body.owner_id or user_id)
        if is_new:
            await create_pipeline_tasks(db, catalog.id)
        return catalog
    raise HTTPException(status_code=422, detail="Provide catalog_id or file_path")
