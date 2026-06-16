from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound, ValidationError
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.knowledge.aggregation.presenter import build_entity_aggregation
from app.services.knowledge.aggregation.vote import VoteService

router = APIRouter(prefix="/api/knowledge/aggregation", tags=["knowledge-aggregation"])


@router.get("/entities/{entity_id}")
async def get_entity_aggregation(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await build_entity_aggregation(db, entity_id)
    if data is None:
        raise NotFound("Entity not found")
    return ApiResponse(data=data)


@router.post("/entities/{entity_id}/refresh-suggestions")
async def refresh_entity_aggregation_suggestions(
    entity_id: int,
    enabled: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    data = await build_entity_aggregation(db, entity_id)
    if data is None:
        raise NotFound("Entity not found")
    if not enabled:
        raise ValidationError("Aggregation suggestions are disabled by default")
    stats = await VoteService.run_vote(db, subject=data["实体"]["standardName"])
    refreshed = await build_entity_aggregation(db, entity_id)
    return ApiResponse(data={"stats": stats, "aggregation": refreshed})
