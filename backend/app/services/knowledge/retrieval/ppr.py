import logging
from collections import defaultdict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PPR_ALPHA = 0.85
PPR_MAX_ITER = 100
PPR_TOL = 1e-6


async def graph_ppr_expansion(
    db: AsyncSession,
    seed_entity_ids: list[int],
    top_k: int = 10,
    alpha: float = PPR_ALPHA,
) -> list[dict]:
    if not seed_entity_ids:
        return []

    edges = await _load_edges(db, seed_entity_ids)
    if not edges:
        return []

    node_ids = set()
    for src, tgt, w in edges:
        node_ids.add(src)
        node_ids.add(tgt)

    node_list = list(node_ids)
    node_index = {nid: i for i, nid in enumerate(node_list)}
    n = len(node_list)

    adj: dict[int, list[tuple[int, float]]] = defaultdict(list)
    out_sum: dict[int, float] = defaultdict(float)
    for src, tgt, w in edges:
        adj[src].append((tgt, w))
        out_sum[src] += w

    seed_set = set(seed_entity_ids) & node_ids
    if not seed_set:
        return []

    p = [0.0] * n
    for sid in seed_set:
        p[node_index[sid]] = 1.0 / len(seed_set)

    r = [0.0] * n
    for sid in seed_set:
        r[node_index[sid]] = 1.0 / len(seed_set)

    for _ in range(PPR_MAX_ITER):
        old_r = r[:]
        r = [0.0] * n
        for i, nid in enumerate(node_list):
            r[i] += (1 - alpha) * p[i]
            if out_sum[nid] > 0 and old_r[i] > 0:
                contrib = alpha * old_r[i] / out_sum[nid]
                for tgt, w in adj[nid]:
                    j = node_index[tgt]
                    r[j] += contrib * w

        delta = sum(abs(r[i] - old_r[i]) for i in range(n))
        if delta < PPR_TOL:
            break

    ranked = sorted(
        [(node_list[i], r[i]) for i in range(n)],
        key=lambda x: x[1],
        reverse=True,
    )

    result = []
    for nid, score in ranked[:top_k]:
        if nid in seed_set:
            continue
        sql = text("""
            SELECT e.id, e.standard_name, e.entity_type
            FROM knowledge_entities e
            WHERE e.id = :eid AND e.confirm_status = 'confirmed'
        """)
        row = await db.execute(sql, {"eid": nid})
        entity = row.first()
        if entity:
            result.append({
                "entity_id": entity.id,
                "entity_name": entity.standard_name,
                "entity_type": entity.entity_type,
                "ppr_score": round(score, 6),
            })

    return result


async def _load_edges(
    db: AsyncSession,
    seed_entity_ids: list[int],
) -> list[tuple[int, int, float]]:
    sql = text("""
        SELECT gn_from.entity_id AS from_id,
               gn_to.entity_id AS to_id,
               ge.weight
        FROM knowledge_graph_edges ge
        JOIN knowledge_graph_nodes gn_from ON gn_from.id = ge.from_node_id
        JOIN knowledge_graph_nodes gn_to ON gn_to.id = ge.to_node_id
        WHERE gn_from.entity_id = ANY(:ids)
           OR gn_to.entity_id = ANY(:ids)
    """)

    result = await db.execute(sql, {"ids": seed_entity_ids})
    rows = result.all()

    edges = []
    for r in rows:
        from_id = int(r.from_id)
        to_id = int(r.to_id)
        weight = float(r.weight or 1.0)
        edges.append((from_id, to_id, weight))

    return edges
