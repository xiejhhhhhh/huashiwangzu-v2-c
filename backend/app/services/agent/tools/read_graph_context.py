from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Entity, GraphEdge, GraphNode
from app.services.agent.tools.registry import BaseTool, ToolResult


class ReadGraphContextTool(BaseTool):
    name = "read_graph_context"
    description = "Read graph context for an entity, including neighbor edges"
    parameters = {
        "type": "object",
        "properties": {
            "entity_id": {"type": "integer", "description": "Entity ID"},
            "limit": {"type": "integer", "description": "Max edges", "default": 20},
        },
        "required": ["entity_id"],
    }

    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        entity_id = kwargs.get("entity_id")
        limit = min(int(kwargs.get("limit", 20)), 50)
        if not entity_id:
            return ToolResult(success=False, error="entity_id is required")

        entity = await db.get(Entity, entity_id)
        if not entity:
            return ToolResult(success=False, error=f"Entity {entity_id} not found")

        node = await _node_for_entity(db, entity_id)
        if not node:
            return ToolResult(data={"entity": _entity_data(entity), "nodes": [], "edges": []})

        rows = await db.execute(
            select(GraphEdge)
            .where((GraphEdge.from_node_id == node.id) | (GraphEdge.to_node_id == node.id))
            .order_by(GraphEdge.weight.desc())
            .limit(limit)
        )
        edges = [await _edge_data(db, node.id, edge) for edge in rows.scalars().all()]
        return ToolResult(data={"entity": _entity_data(entity), "node_id": node.id, "edges": edges})


async def _node_for_entity(db: AsyncSession, entity_id: int) -> GraphNode | None:
    result = await db.execute(select(GraphNode).where(GraphNode.entity_id == entity_id))
    return result.scalar_one_or_none()


async def _edge_data(db: AsyncSession, seed_node_id: int, edge: GraphEdge) -> dict:
    neighbor_id = edge.to_node_id if edge.from_node_id == seed_node_id else edge.from_node_id
    node = await db.get(GraphNode, neighbor_id)
    entity = await db.get(Entity, node.entity_id) if node else None
    return {
        "edge_id": edge.id,
        "relation": edge.relation,
        "weight": edge.weight,
        "support_chunk_ids": edge.support_chunk_ids or {},
        "neighbor_node_id": neighbor_id,
        "neighbor_entity": _entity_data(entity) if entity else None,
    }


def _entity_data(entity: Entity) -> dict:
    return {
        "entity_id": entity.id,
        "standard_name": entity.standard_name,
        "entity_type": entity.entity_type,
        "confirm_status": entity.confirm_status,
    }
