import logging

logger = logging.getLogger(__name__)


async def rerank_results(
    query: str,
    candidates: list[dict],
    top_k: int = 10,
) -> list[dict]:
    if not candidates:
        return []

    passages = []
    for c in candidates:
        text = c.get("fusion_text", "") or ""
        summary = c.get("summary", "") or ""
        combined = text[:512] + (" " + summary[:256] if summary else "")
        passages.append(combined[:768])

    try:
        scores = await _call_reranker(query, passages)
    except Exception as e:
        logger.warning("Reranker unavailable, using combined scores as-is: %s", e)
        rerank_used = False
        for i, c in enumerate(candidates):
            cs = c.get("scores", {})
            c["rerank_score"] = cs.get("combined", 0.0) if isinstance(cs, dict) else float(cs or 0)
            c["rerank_used"] = rerank_used
        ranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
        return ranked[:top_k]

    rerank_used = True
    for i, c in enumerate(candidates):
        c["rerank_score"] = round(float(scores[i]), 4) if i < len(scores) else 0.0
        c["rerank_used"] = rerank_used

    ranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
    return ranked[:top_k]


async def _call_reranker(query: str, passages: list[str]) -> list[float]:
    from app.services.model_services import rerank as config_rerank

    try:
        results = await config_rerank(query, passages)
    except Exception as e:
        logger.warning("Reranker via model_services failed: %s", e)
        raise

    scores = [0.0] * len(passages)
    for r in results:
        idx = r.get("index")
        if idx is not None and 0 <= idx < len(passages):
            scores[idx] = r.get("relevance_score", 0.0)

    return scores
