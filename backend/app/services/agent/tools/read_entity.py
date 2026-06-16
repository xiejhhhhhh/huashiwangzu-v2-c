from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.agent.tools.registry import BaseTool, ToolResult, tool_registry
from app.models.knowledge import Entity, EntityAlias, Attribute, GraphNode, GraphEdge


class ReadEntityTool(BaseTool):
    name = "read_entity"
    description = "Read entity details with graph neighbors and attributes"
    parameters = {
        "type": "object",
        "properties": {
            "entity_id": {"type": "integer", "description": "Entity ID"},
        },
        "required": ["entity_id"],
    }

    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        entity_id = kwargs.get("entity_id")
        if not entity_id:
            return ToolResult(success=False, error="entity_id is required")

        entity = await db.get(Entity, entity_id)
        if not entity:
            return ToolResult(success=False, error=f"Entity {entity_id} not found")

        # Aliases
        alias_result = await db.execute(
            select(EntityAlias).where(EntityAlias.entity_id == entity_id)
        )
        aliases = [{"alias": a.alias, "type": a.alias_type} for a in alias_result.scalars().all()]

        # Attributes
        attr_result = await db.execute(
            select(Attribute).where(Attribute.subject == entity.standard_name)
        )
        attributes = [{"name": a.attr_name, "value": a.attr_value, "source_page": a.source_page}
                      for a in attr_result.scalars().all()]

        # Graph node
        node_result = await db.execute(
            select(GraphNode).where(GraphNode.entity_id == entity_id)
        )
        node = node_result.scalar_one_or_none()
        neighbors = []
        if node:
            edge_result = await db.execute(
                select(GraphEdge).where(
                    (GraphEdge.from_node_id == node.id) | (GraphEdge.to_node_id == node.id)
                )
            )
            for edge in edge_result.scalars().all():
                neighbor_id = edge.to_node_id if edge.from_node_id == node.id else edge.from_node_id
                neighbor_node = await db.get(GraphNode, neighbor_id)
                neighbor_name = ""
                if neighbor_node:
                    neighbor_entity = await db.get(Entity, neighbor_node.entity_id)
                    neighbor_name = neighbor_entity.standard_name if neighbor_entity else ""
                neighbors.append({
                    "entity_name": neighbor_name,
                    "relation": edge.relation,
                    "weight": float(edge.weight),
                })

        return ToolResult(data={
            "entity_id": entity.id,
            "standard_name": entity.standard_name,
            "entity_type": entity.entity_type,
            "confirm_status": entity.confirm_status,
            "occurrence_count": entity.occurrence_count,
            "aliases": aliases,
            "attributes": attributes,
            "graph_neighbors": neighbors,
        })
