from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Chunk, Entity, GraphEdge


async def find_cooccurring_chunks(db: AsyncSession, name_a: str, name_b: str) -> list[int]:
    result = await db.execute(
        select(Chunk.id).where(
            and_(
                Chunk.content.ilike(f"%{name_a}%"),
                Chunk.content.ilike(f"%{name_b}%"),
            )
        ).limit(100)
    )
    return [row[0] for row in result.all()]


def infer_relation(entity_a: Entity, entity_b: Entity) -> str:
    type_a, type_b = entity_a.entity_type, entity_b.entity_type
    relation_map = {
        ("brand", "product"): "produces",
        ("product", "ingredient"): "contains",
        ("product", "effect"): "claims",
        ("brand", "ingredient"): "uses",
        ("brand", "effect"): "markets",
        ("product", "organization"): "manufactured_by",
        ("ingredient", "effect"): "contributes_to",
    }
    direct = relation_map.get((type_a, type_b))
    if direct:
        return direct
    reverse = relation_map.get((type_b, type_a))
    if reverse:
        return f"reverse_{reverse}"
    return "co_occurs_with"


async def edge_exists(
    db: AsyncSession,
    from_node_id: int,
    to_node_id: int,
    relation: str,
) -> bool:
    direct = await db.execute(
        select(GraphEdge).where(
            and_(
                GraphEdge.from_node_id == from_node_id,
                GraphEdge.to_node_id == to_node_id,
                GraphEdge.relation == relation,
            )
        )
    )
    if direct.scalar_one_or_none():
        return True
    reverse = await db.execute(
        select(GraphEdge).where(
            and_(
                GraphEdge.from_node_id == to_node_id,
                GraphEdge.to_node_id == from_node_id,
                GraphEdge.relation == relation,
            )
        )
    )
    return reverse.scalar_one_or_none() is not None
