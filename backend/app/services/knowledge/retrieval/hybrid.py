import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.knowledge import SearchResult
from .vector_recall import vector_recall
from .bm25_recall import bm25_recall
from .label_recall import label_recall
from .dict_recall import dict_recall
from .graph_recall import graph_recall
from .rrf import rrf_fusion
from .reranker import rerank_results
from .ppr import graph_ppr_expansion
from .result_builder import build_lightweight_index

logger = logging.getLogger(__name__)


async def hybrid_search(
    db: AsyncSession,
    query: str,
    top_k: int = 20,
    enable_vector: bool = True,
    enable_bm25: bool = True,
    enable_label: bool = True,
    enable_dict: bool = True,
    enable_graph: bool = True,
    enable_rerank: bool = True,
    enable_ppr: bool = True,
    weights: dict[str, float] | None = None,
) -> SearchResult:
    recall_tasks = {}
    recall_used = []

    if enable_vector:
        recall_tasks["vector"] = vector_recall(db, query, top_k)
    if enable_bm25:
        recall_tasks["bm25"] = bm25_recall(db, query, top_k)
    if enable_label:
        recall_tasks["label"] = label_recall(db, query, top_k)
    if enable_dict:
        recall_tasks["dict"] = dict_recall(db, query, top_k)

    results: dict[str, list[dict]] = {}
    for name, coro in recall_tasks.items():
        try:
            async with db.begin_nested():
                items = await coro
            if items:
                results[name] = items
                recall_used.append(name)
                logger.info("%s_recall returned %d items", name, len(items))
        except Exception as e:
            logger.error("%s_recall failed: %s", name, e)

    if not results:
        return SearchResult(items=[], total=0, query=query, recall_used=[], rerank_used=False, ppr_used=False)

    fused = rrf_fusion(results, top_k=top_k * 2, weights=weights)

    if enable_graph and fused:
        entity_ids = await _extract_entity_ids(db, fused)
        if entity_ids:
            try:
                graph_items = await graph_recall(db, entity_ids, top_k)
                if graph_items:
                    results["graph"] = graph_items
                    recall_used.append("graph")
                    fused = rrf_fusion(results, top_k=top_k * 2, weights=weights)
            except Exception as e:
                logger.error("graph_recall failed: %s", e)

    ppr_used = False
    if enable_ppr and fused:
        entity_ids = await _extract_entity_ids(db, fused)
        if entity_ids:
            try:
                ppr_results = await graph_ppr_expansion(db, entity_ids, top_k=10)
                if ppr_results:
                    for item in fused:
                        matching = [p for p in ppr_results if p.get("entity_id") == item.get("source_id")]
                        if matching:
                            item.setdefault("scores", {})["ppr_score"] = matching[0]["ppr_score"]
                        item["ppr_neighbors"] = [
                            p for p in ppr_results
                            if p.get("entity_id") != item.get("source_id")
                        ][:5]
                    ppr_used = True
            except Exception as e:
                logger.error("PPR expansion failed: %s", e)

    rerank_used = False
    if enable_rerank and fused:
        try:
            fused = await rerank_results(query, fused, top_k)
            rerank_used = True
        except Exception as e:
            logger.error("Reranker failed, using RRF scores: %s", e)

    items = [build_lightweight_index(item) for item in fused[:top_k]]

    return SearchResult(
        items=items,
        total=len(items),
        query=query,
        recall_used=recall_used,
        rerank_used=rerank_used,
        ppr_used=ppr_used,
    )


async def _extract_entity_ids(db: AsyncSession, fused: list[dict]) -> list[int]:
    from sqlalchemy import bindparam, text
    source_ids = [int(f["source_id"]) for f in fused if str(f.get("source_id", "")).isdigit()]
    if not source_ids:
        return []

    sql = text("""
        SELECT DISTINCT e.id
        FROM knowledge_entities e
        JOIN chunks c ON c.source_fusion_id IN :source_ids
        WHERE e.confirm_status = 'confirmed'
        LIMIT 50
    """).bindparams(bindparam("source_ids", expanding=True))

    try:
        result = await db.execute(sql, {"source_ids": [sid for sid in source_ids if sid > 0]})
        return [r[0] for r in result.all()]
    except Exception as e:
        logger.warning("Extract entity IDs failed: %s", e)
        return []
