from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.knowledge import Catalog
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.knowledge.analysis_presenter import build_analysis_result

router = APIRouter(prefix="/api/knowledge/analysis-results", tags=["knowledge-analysis-results"])


@router.get("/{catalog_id}")
async def get_analysis_result(
    catalog_id: int,
    include_sources: bool = True,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    catalog = await db.get(Catalog, catalog_id)
    if not catalog:
        raise NotFound("Knowledge file not found")
    safe_limit = min(max(limit, 1), 500)
    return ApiResponse(data=await build_analysis_result(db, catalog, include_sources, safe_limit))
