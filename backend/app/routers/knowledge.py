from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.knowledge import CatalogResponse, SearchRequest, SearchResult, PageFusionResult
from app.services.knowledge.retrieval.page_fusion_reader import get_page_fusion as get_fusion_service
from app.middleware.auth import require_permission
from app.models.user import User
from app.models.knowledge import Catalog, PageSource, PageFusion
from app.services import knowledge_service
from app.core.exceptions import NotFound

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/page-fusion")
async def get_page_fusion(
    fusion_id: int | None = None,
    catalog_id: int | None = None,
    page_num: int | None = None,
    offset: int = 0,
    limit: int = 2000,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    if fusion_id is None and (catalog_id is None or page_num is None):
        raise HTTPException(
            status_code=422,
            detail="Provide either fusion_id, or catalog_id + page_num",
        )

    result: PageFusionResult | None = await get_fusion_service(
        db, fusion_id=fusion_id, catalog_id=catalog_id,
        page_num=page_num, offset=offset, limit=limit,
    )
    if not result:
        raise NotFound("Page fusion not found")

    return ApiResponse(data=result.model_dump())


@router.post("/search")
async def search(
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    results = await knowledge_service.hybrid_search(db, body.query, body.top_k)
    return ApiResponse(data=results)


@router.get("/catalogs/{catalog_id}")
async def get_catalog_status(
    catalog_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await db.execute(select(Catalog).where(Catalog.id == catalog_id))
    catalog = result.scalar_one_or_none()
    if not catalog:
        raise NotFound(f"Catalog {catalog_id} not found")

    source_count_result = await db.execute(
        select(PageSource.id).where(PageSource.catalog_id == catalog_id)
    )
    source_count = len(source_count_result.all())

    fusion_count_result = await db.execute(
        select(PageFusion.id).where(PageFusion.catalog_id == catalog_id)
    )
    fusion_count = len(fusion_count_result.all())

    return ApiResponse(data={
        "id": catalog.id,
        "file_name": catalog.file_name,
        "file_size": catalog.file_size,
        "mime_type": catalog.mime_type,
        "channel_type": catalog.channel_type,
        "status": catalog.status,
        "error": catalog.error,
        "page_sources": source_count,
        "page_fusions": fusion_count,
        "created_at": catalog.created_at.isoformat() if catalog.created_at else None,
    })
