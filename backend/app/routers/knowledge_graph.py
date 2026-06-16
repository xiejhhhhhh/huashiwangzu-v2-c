from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.knowledge import Entity, GraphEdge, GraphNode
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.knowledge.governance_presenter import (
    edge_dict,
    entity_dict,
    node_dict,
    paginate,
)

router = APIRouter(prefix="/api/knowledge/graph", tags=["knowledge-graph"])


async def _node_with_edges(db: AsyncSession, node: GraphNode) -> dict:
    result = await db.execute(
        select(GraphEdge).where(
            or_(GraphEdge.from_node_id == node.id, GraphEdge.to_node_id == node.id)
        )
    )
    entity = await db.get(Entity, node.entity_id)
    return {
        "entity": entity_dict(entity) if entity else None,
        "node": node_dict(node),
        "edges": [edge_dict(edge) for edge in result.scalars().all()],
    }


@router.get("/search")
async def search_graph_nodes(
    q: str = Query("", max_length=128),
    node_type: str | None = None,
    page: int = 1,
    pageSize: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    query = select(GraphNode).join(Entity, GraphNode.entity_id == Entity.id)
    if q:
        like = f"%{q}%"
        query = query.where(Entity.standard_name.ilike(like))
    if node_type:
        query = query.where(GraphNode.node_type == node_type)
    query = query.order_by(GraphNode.occurrence_count.desc(), GraphNode.id.desc())
    data = await paginate(db, query, page, pageSize)
    entity_ids = [node.entity_id for node in data["items"]]
    entities = await db.execute(select(Entity).where(Entity.id.in_(entity_ids)))
    entity_map = {entity.id: entity_dict(entity) for entity in entities.scalars()}
    data["items"] = [
        {"node": node_dict(node), "entity": entity_map.get(node.entity_id)}
        for node in data["items"]
    ]
    return ApiResponse(data=data)


@router.get("/by-business/{node_type}/{business_id}")
async def get_graph_by_business(
    node_type: str,
    business_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    node = (
        await db.execute(
            select(GraphNode).where(
                GraphNode.node_type == node_type,
                GraphNode.entity_id == business_id,
            )
        )
    ).scalar_one_or_none()
    if not node:
        raise NotFound("Graph node not found")
    return ApiResponse(data=await _node_with_edges(db, node))
