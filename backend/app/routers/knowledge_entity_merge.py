from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.knowledge import EntityMergeRequest
from app.services.knowledge.aggregation.disambig import DisambiguationService
from app.services.knowledge.aggregation.merge_ops import execute_merge

router = APIRouter(prefix="/api/knowledge/entities", tags=["knowledge-entity-merge"])


@router.post("/disambiguation/scan")
async def scan_disambiguation_candidates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    candidates = await DisambiguationService.scan_candidates(db)
    return ApiResponse(data={"count": len(candidates)})


@router.post("/merge")
async def merge_entities(
    body: EntityMergeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    if body.from_entity_id == body.to_entity_id:
        raise ValidationError("Cannot merge an entity into itself")
    merge_record = await execute_merge(
        db, body.from_entity_id, body.to_entity_id, confidence=1.0
    )
    if body.reason:
        merge_record.reason = body.reason
    await db.commit()
    await db.refresh(merge_record)
    return ApiResponse(data={
        "id": merge_record.id,
        "fromEntityId": merge_record.from_entity_id,
        "toEntityId": merge_record.to_entity_id,
        "reason": merge_record.reason,
    })
