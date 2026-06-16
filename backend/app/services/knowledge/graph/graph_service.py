"""
L6 图谱节点/边构建服务
从干净词典 + 证据构建:
- 节点: occurrence_count
- 边: relation + support_chunk_ids (证据回溯)
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    Entity, GraphNode, GraphEdge,
)
from app.services.knowledge.graph.edge_ops import (
    edge_exists,
    find_cooccurring_chunks,
    infer_relation,
)

logger = logging.getLogger(__name__)


class GraphService:

    @staticmethod
    async def build_nodes(db: AsyncSession, entity_ids: list[int] | None = None) -> list[GraphNode]:
        """从已确认实体建图谱节点, 带 occurrence_count"""
        query = select(Entity).where(Entity.confirm_status == "confirmed")
        if entity_ids:
            query = query.where(Entity.id.in_(entity_ids))
        result = await db.execute(query)
        entities = result.scalars().all()

        nodes: list[GraphNode] = []
        for entity in entities:
            existing = await db.execute(
                select(GraphNode).where(GraphNode.entity_id == entity.id)
            )
            if existing.scalar_one_or_none():
                continue

            node = GraphNode(
                entity_id=entity.id,
                node_type=entity.entity_type,
                occurrence_count=entity.occurrence_count or 0,
            )
            db.add(node)
            nodes.append(node)

        if nodes:
            await db.commit()
            for n in nodes:
                await db.refresh(n)

        logger.info("Built %d graph nodes", len(nodes))
        return nodes

    @staticmethod
    async def build_edges(
        db: AsyncSession,
        min_cooccurrence: int = 1,
    ) -> list[GraphEdge]:
        """基于实体共现 + 证据构建图谱边"""
        nodes = await db.execute(select(GraphNode))
        node_map: dict[int, GraphNode] = {n.entity_id: n for n in nodes.scalars().all()}

        if len(node_map) < 2:
            logger.info("Less than 2 nodes, skipping edge building")
            return []

        # 批量加载实体
        entity_ids = list(node_map.keys())
        entities_result = await db.execute(
            select(Entity).where(Entity.id.in_(entity_ids))
        )
        entity_map: dict[int, Entity] = {e.id: e for e in entities_result.scalars().all()}

        edges: list[GraphEdge] = []
        pairs = list(node_map.items())
        for i, (eid_a, node_a) in enumerate(pairs):
            entity_a = entity_map.get(eid_a)
            if not entity_a:
                continue
            for eid_b, node_b in pairs[i + 1:]:
                entity_b = entity_map.get(eid_b)
                if not entity_b:
                    continue

                support_chunk_ids = await find_cooccurring_chunks(
                    db, entity_a.standard_name, entity_b.standard_name
                )
                if len(support_chunk_ids) < min_cooccurrence:
                    continue

                relation = infer_relation(entity_a, entity_b)
                if await edge_exists(db, node_a.id, node_b.id, relation):
                    continue

                edge = GraphEdge(
                    from_node_id=node_a.id,
                    to_node_id=node_b.id,
                    relation=relation,
                    support_chunk_ids=support_chunk_ids,
                    weight=round(len(support_chunk_ids) * 0.1 + 0.5, 2),
                )
                db.add(edge)
                edges.append(edge)

        if edges:
            await db.commit()
            for e in edges:
                await db.refresh(e)

        logger.info("Built %d graph edges", len(edges))
        return edges

    async def get_node_by_entity(db: AsyncSession, entity_id: int) -> GraphNode | None:
        result = await db.execute(
            select(GraphNode).where(GraphNode.entity_id == entity_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_edges_for_node(db: AsyncSession, node_id: int) -> list[dict]:
        result = await db.execute(
            select(GraphEdge).where(
                (GraphEdge.from_node_id == node_id) | (GraphEdge.to_node_id == node_id)
            )
        )
        edges = result.scalars().all()
        output = []
        for e in edges:
            output.append({
                "edge_id": e.id,
                "from_node_id": e.from_node_id,
                "to_node_id": e.to_node_id,
                "relation": e.relation,
                "support_chunk_ids": e.support_chunk_ids or [],
                "weight": e.weight,
            })
        return output
