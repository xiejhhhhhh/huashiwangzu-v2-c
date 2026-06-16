import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "vector": 0.35,
    "graph": 0.25,
    "bm25": 0.20,
    "label": 0.10,
    "dict": 0.05,
    "freshness": 0.05,
}

RRF_K = 60


def rrf_fusion(
    recall_results: dict[str, list[dict]],
    top_k: int = 20,
    weights: dict[str, float] | None = None,
) -> list[dict]:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    score_sums: dict[int, dict] = defaultdict(lambda: {
        "scores": {k: 0.0 for k in w},
        "recall_types": set(),
        "details": {},
    })

    for recall_type, items in recall_results.items():
        if not items:
            continue
        for rank, item in enumerate(items):
            fid = item.get("source_id")
            if not fid:
                continue

            entry = score_sums[fid]
            rrf_score = 1.0 / (RRF_K + rank + 1)
            entry["scores"][recall_type] = max(
                entry["scores"][recall_type], rrf_score
            )
            entry["recall_types"].add(recall_type)

            for k, v in item.items():
                if k not in ("score", "recall_type"):
                    entry["details"].setdefault(k, v)

    fused = []
    for fid, entry in score_sums.items():
        combined = 0.0
        individual_scores = {}
        for rtype, rrf_val in entry["scores"].items():
            weighted = rrf_val * w.get(rtype, 0.1)
            individual_scores[rtype] = round(rrf_val, 4)
            combined += weighted

        fused.append({
            "source_id": fid,
            "catalog_id": entry["details"].get("catalog_id"),
            "page_num": entry["details"].get("page_num"),
            "fusion_text": entry["details"].get("fusion_text", ""),
            "summary": entry["details"].get("summary"),
            "labels": entry["details"].get("labels"),
            "attributes": entry["details"].get("attributes"),
            "recall_types": sorted(entry["recall_types"]),
            "scores": {
                "combined": round(combined, 4),
                **individual_scores,
            },
        })

    fused.sort(key=lambda x: x["scores"]["combined"], reverse=True)
    return fused[:top_k]
