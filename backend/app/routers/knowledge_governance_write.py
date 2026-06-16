from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.knowledge import Entity, EntityAlias, ExtractCandidate
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.knowledge import (
    CandidateDecisionRequest,
    EntityAliasCreateRequest,
    EntityCreateRequest,
    EntityUpdateRequest,
)
from app.services.knowledge.dictionary.entity_service import add_alias, create_entity, find_entity
from app.services.knowledge.governance_presenter import entity_dict

router = APIRouter(prefix="/api/knowledge", tags=["knowledge-governance-write"])


@router.post("/candidates/{candidate_id}/confirm")
async def confirm_candidate(
    candidate_id: int,
    body: CandidateDecisionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    candidate = await db.get(ExtractCandidate, candidate_id)
    if not candidate:
        raise NotFound("Candidate not found")
    candidate.verdict_status = 1
    candidate.extra = candidate.extra or {}
    candidate.extra["decision_reason"] = body.reason
    if body.target_entity_id:
        candidate.extra["target_entity_id"] = body.target_entity_id
    await db.commit()
    return ApiResponse(data={"message": "Candidate confirmed"})


@router.post("/candidates/{candidate_id}/ignore")
async def ignore_candidate(
    candidate_id: int,
    body: CandidateDecisionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    candidate = await db.get(ExtractCandidate, candidate_id)
    if not candidate:
        raise NotFound("Candidate not found")
    candidate.verdict_status = 2
    candidate.extra = candidate.extra or {}
    candidate.extra["decision_reason"] = body.reason
    await db.commit()
    return ApiResponse(data={"message": "Candidate ignored"})


@router.post("/entities")
async def create_knowledge_entity(
    body: EntityCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    existing = await find_entity(db, body.standard_name)
    if existing:
        return ApiResponse(data=entity_dict(existing))
    entity = await create_entity(db, body.standard_name, body.entity_type, body.confirm_status)
    await db.commit()
    await db.refresh(entity)
    return ApiResponse(data=entity_dict(entity))


@router.put("/entities/{entity_id}")
async def update_knowledge_entity(
    entity_id: int,
    body: EntityUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    entity = await db.get(Entity, entity_id)
    if not entity:
        raise NotFound("Entity not found")
    if body.standard_name is not None:
        entity.standard_name = body.standard_name
    if body.entity_type is not None:
        entity.entity_type = body.entity_type
    if body.confirm_status is not None:
        entity.confirm_status = body.confirm_status
    await db.commit()
    await db.refresh(entity)
    return ApiResponse(data=entity_dict(entity))


@router.post("/entities/aliases")
async def create_entity_alias(
    body: EntityAliasCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    alias = await add_alias(db, body.entity_id, body.alias, body.alias_type)
    if not alias:
        return ApiResponse(data={"message": "Alias already exists"})
    await db.commit()
    await db.refresh(alias)
    return ApiResponse(data={"id": alias.id, "entityId": alias.entity_id, "alias": alias.alias, "aliasType": alias.alias_type})


@router.post("/entities/aliases/{alias_id}/disable")
async def disable_entity_alias(
    alias_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    alias = await db.get(EntityAlias, alias_id)
    if not alias:
        raise NotFound("Alias not found")
    alias.alias_type = "disabled"
    await db.commit()
    return ApiResponse(data={"message": "Alias disabled"})

