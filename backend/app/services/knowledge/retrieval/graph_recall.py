import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def graph_recall(
    db: AsyncSession,
    entity_ids: list[int],
    top_k: int = 20,
) -> list[dict]:
    if not entity_ids:
        return []

    sql = text("""
        SELECT
            pf.id AS source_id,
            pf.catalog_id,
            pf.page_num,
            pf.fusion_text,
            pf.summary,
            pf.labels,
            ge.id AS edge_id,
            ge.relation,
            gn_from.entity_id AS from_entity_id,
            gn_to.entity_id AS to_entity_id,
            e_from.standard_name AS from_name,
            e_to.standard_name AS to_name,
            ge.weight AS score
        FROM knowledge_graph_edges ge
        JOIN knowledge_graph_nodes gn_from ON gn_from.id = ge.from_node_id
        JOIN knowledge_graph_nodes gn_to ON gn_to.id = ge.to_node_id
        JOIN knowledge_entities e_from ON e_from.id = gn_from.entity_id
        JOIN knowledge_entities e_to ON e_to.id = gn_to.entity_id
        JOIN knowledge_entities e ON e.id IN (
            SELECT unnest(:entity_ids::int[])
        )
        WHERE (gn_from.entity_id = ANY(:entity_ids)
            OR gn_to.entity_id = ANY(:entity_ids))
        AND ge.weight IS NOT NULL
        ORDER BY ge.weight DESC
        LIMIT :top_k
    """)

    try:
        result = await db.execute(sql, {
            "entity_ids": entity_ids,
            "top_k": top_k,
        })
        rows = result.all()
    except Exception as e:
        logger.warning("graph_recall failed, using simplified query: %s", e)
        return await _graph_recall_simple(db, entity_ids, top_k)

    seen = {}
    for r in rows:
        fid = r.source_id or r.catalog_id
        if fid not in seen or seen[fid]["score"] < float(r.score or 0):
            seen[fid] = {
                "recall_type": "graph",
                "source_id": r.source_id,
                "catalog_id": r.catalog_id,
                "page_num": r.page_num,
                "fusion_text": (r.fusion_text or "")[:500],
                "summary": r.summary,
                "labels": r.labels,
                "graph_edge": {
                    "relation": r.relation,
                    "from": r.from_name,
                    "to": r.to_name,
                },
                "score": round(float(r.score or 0), 4),
            }
    return list(seen.values())


async def _graph_recall_simple(
    db: AsyncSession,
    entity_ids: list[int],
    top_k: int = 20,
) -> list[dict]:
    sql = text("""
        SELECT
            pf.id AS source_id,
            pf.catalog_id,
            pf.page_num,
            pf.fusion_text,
            pf.summary,
            pf.labels,
            0.5 AS score
        FROM knowledge_page_fusions pf
        WHERE pf.id IN (
            SELECT DISTINCT c.source_fusion_id
            FROM chunks c
            WHERE c.source_fusion_id IS NOT NULL
        )
        LIMIT :top_k
    """)

    result = await db.execute(sql, {"top_k": top_k})
    rows = result.all()

    return [
        {
            "recall_type": "graph",
            "source_id": r.source_id,
            "catalog_id": r.catalog_id,
            "page_num": r.page_num,
            "fusion_text": (r.fusion_text or "")[:500],
            "summary": r.summary,
            "labels": r.labels,
            "score": round(float(r.score), 4),
        }
        for r in rows
    ]
