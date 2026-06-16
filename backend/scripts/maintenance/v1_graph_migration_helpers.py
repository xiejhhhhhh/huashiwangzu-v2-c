import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("migrate_v1.graph_helpers")


def match_entity_id(
    node: Any,
    title: str,
    id_map: dict[Any, Any],
    entities: list[Any],
) -> Any | None:
    entity_id = id_map.get(node.get("业务ID")) if node.get("业务ID") else None
    if entity_id:
        return entity_id
    return next(
        (
            value
            for key, value in id_map.items()
            if any(item["标准名"] == title for item in entities if item["词典ID"] == key)
        ),
        None,
    )


async def migrate_nodes(
    db: AsyncSession,
    id_map: dict[Any, Any],
    entities: list[Any],
    nodes: list[Any],
) -> dict[Any, Any]:
    node_map: dict[Any, Any] = {}
    for node in nodes:
        title = node.get("标题", "") or ""
        entity_id = match_entity_id(node, title, id_map, entities) if title else None
        if not entity_id:
            continue
        try:
            result = await db.execute(
                text(
                    """
                    INSERT INTO knowledge_graph_nodes
                    (entity_id, node_type, occurrence_count)
                    VALUES (:entity_id, COALESCE(:ntype, 'unknown'), 1)
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """
                ),
                {"entity_id": entity_id, "ntype": node.get("节点类型")},
            )
            new_id = result.scalar_one_or_none()
            if new_id:
                node_map[node["节点ID"]] = new_id
        except Exception as exc:
            logger.warning("Graph node insert failed for %s: %s", title, exc)
    await db.commit()
    return node_map


async def migrate_edges(
    db: AsyncSession,
    node_map: dict[Any, Any],
    edges: list[Any],
) -> int:
    count = 0
    for edge in edges:
        source_id = node_map.get(edge["起点节点ID"])
        target_id = node_map.get(edge["终点节点ID"])
        if not source_id or not target_id:
            continue
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO knowledge_graph_edges
                    (source_node_id, target_node_id, relation_type, weight)
                    VALUES (:source_id, :target_id, COALESCE(:rtype, 'related'), 1.0)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "rtype": edge.get("关系类型"),
                },
            )
            count += 1
        except Exception as exc:
            logger.warning("Graph edge insert failed: %s", exc)
    await db.commit()
    return count
