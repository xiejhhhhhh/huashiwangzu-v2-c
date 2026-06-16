from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.knowledge import Entity, Evidence, ExtractCandidate, GraphEdge, GraphNode
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.knowledge.governance_presenter import (
    candidate_dict,
    edge_dict,
    entity_dict,
    evidence_dict,
    node_dict,
    paginate,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge-governance"])


@router.get("/evidences")
async def list_evidences(
    catalog_id: int | None = None,
    page: int = 1,
    pageSize: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    query = select(Evidence).order_by(Evidence.id.desc())
    if catalog_id:
        query = query.where(Evidence.catalog_id == catalog_id)
    data = await paginate(db, query, page, pageSize)
    data["items"] = [evidence_dict(e) for e in data["items"]]
    return ApiResponse(data=data)


@router.get("/evidences/{evidence_id}")
async def get_evidence(
    evidence_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    evidence = await db.get(Evidence, evidence_id)
    if not evidence:
        raise NotFound("Evidence not found")
    return ApiResponse(data=evidence_dict(evidence))


@router.get("/candidates")
async def list_candidates(
    status: int | None = None,
    page: int = 1,
    pageSize: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    query = select(ExtractCandidate).order_by(ExtractCandidate.id.desc())
    if status is not None:
        query = query.where(ExtractCandidate.verdict_status == status)
    data = await paginate(db, query, page, pageSize)
    data["items"] = [candidate_dict(c) for c in data["items"]]
    return ApiResponse(data=data)


@router.get("/candidates/pending-count")
async def count_pending_candidates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    count = await db.scalar(select(func.count(ExtractCandidate.id)).where(ExtractCandidate.verdict_status == 0))
    return ApiResponse(data={"count": count or 0})


@router.get("/candidates/{candidate_id}")
async def get_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    candidate = await db.get(ExtractCandidate, candidate_id)
    if not candidate:
        raise NotFound("Candidate not found")
    return ApiResponse(data=candidate_dict(candidate))


@router.get("/graph/overview")
async def graph_overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    node_count = await db.scalar(select(func.count(GraphNode.id)))
    edge_count = await db.scalar(select(func.count(GraphEdge.id)))
    latest = await db.execute(select(GraphNode).order_by(GraphNode.id.desc()).limit(10))
    return ApiResponse(data={
        "nodeCount": node_count or 0,
        "edgeCount": edge_count or 0,
        "latestNodes": [node_dict(n) for n in latest.scalars().all()],
    })


@router.get("/graph/nodes/{node_id}")
async def get_graph_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    node = await db.get(GraphNode, node_id)
    if not node:
        raise NotFound("Graph node not found")
    edges = await db.execute(select(GraphEdge).where(or_(GraphEdge.from_node_id == node_id, GraphEdge.to_node_id == node_id)))
    return ApiResponse(data={"node": node_dict(node), "edges": [edge_dict(e) for e in edges.scalars().all()]})


@router.get("/graph/entities/{entity_id}")
async def get_entity_graph(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    node = (await db.execute(select(GraphNode).where(GraphNode.entity_id == entity_id))).scalar_one_or_none()
    if not node:
        raise NotFound("Graph node not found")
    entity = await db.get(Entity, entity_id)
    edges = await db.execute(select(GraphEdge).where(or_(GraphEdge.from_node_id == node.id, GraphEdge.to_node_id == node.id)))
    return ApiResponse(data={
        "entity": entity_dict(entity) if entity else None,
        "node": node_dict(node),
        "edges": [edge_dict(e) for e in edges.scalars().all()],
    })

