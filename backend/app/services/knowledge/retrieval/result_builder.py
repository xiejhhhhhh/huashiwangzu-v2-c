from app.schemas.knowledge import LightweightIndex, ScoreDetail


def build_score_detail(item: dict) -> ScoreDetail:
    scores = item.get("scores", {})
    if not isinstance(scores, dict):
        return ScoreDetail(combined=float(scores or 0))
    return ScoreDetail(
        vector=scores.get("vector", 0.0),
        bm25=scores.get("bm25", 0.0),
        label=scores.get("label", 0.0),
        dict_score=scores.get("dict", 0.0),
        graph=scores.get("graph", 0.0),
        freshness=scores.get("freshness", 0.0),
        combined=scores.get("combined", 0.0),
        rerank_score=item.get("rerank_score"),
        ppr_score=scores.get("ppr_score"),
    )


def build_lightweight_index(item: dict) -> LightweightIndex:
    recall_type = item.get("recall_types", item.get("recall_type", "unknown"))
    return LightweightIndex(
        recall_type=",".join(sorted(recall_type)) if isinstance(recall_type, (list, set)) else str(recall_type),
        source_id=item.get("source_id", 0),
        catalog_id=item.get("catalog_id", 0),
        page_num=item.get("page_num"),
        summary=item.get("summary"),
        subject=item.get("subject"),
        attribute_hints=item.get("attribute_hints"),
        labels=item.get("labels"),
        graph_neighbors=item.get("ppr_neighbors"),
        evidence_types=item.get("recall_types", []),
        scores=build_score_detail(item),
        fusion_text_preview=item.get("fusion_text", ""),
        deep_read_url=f"/api/knowledge/page-fusion?fusion_id={item.get('source_id', 0)}",
        source_url=f"/api/files/{item.get('catalog_id', 0)}",
    )
