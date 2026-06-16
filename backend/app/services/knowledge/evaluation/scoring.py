import time
from typing import Any

from app.schemas.knowledge import SearchResult


def result_text(item: Any) -> str:
    parts = [
        item.summary or "",
        item.subject or "",
        item.fusion_text_preview or "",
    ]
    if item.labels:
        parts.extend(item.labels)
    return " ".join(parts)


def score_question(question: dict, result: SearchResult, started_at: float) -> dict:
    expected = question.get("期望关键词") or []
    forbidden = question.get("禁止关键词") or []
    minimum = int(question.get("最低命中数") or 1)
    texts = [result_text(item) for item in result.items]
    joined = "\n".join(texts)
    expected_hits = [word for word in expected if word and word in joined]
    forbidden_hits = [word for word in forbidden if word and word in joined]
    hit_ratio = min(1.0, len(expected_hits) / max(minimum, 1))
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    quantity_score = 1.0 if result.total > 0 else 0.0
    speed_score = max(0.0, 1.0 - max(0, latency_ms - 500) / 2000)
    clean_score = 0.0 if forbidden_hits else 1.0
    score = round((hit_ratio * 55) + (quantity_score * 15) + (speed_score * 15) + (clean_score * 15), 2)
    passed = len(expected_hits) >= minimum and not forbidden_hits
    return {
        "id": question.get("id", ""),
        "question": question.get("问题", ""),
        "category": question.get("类型", ""),
        "score": score,
        "passed": passed,
        "expectedHits": expected_hits,
        "forbiddenHits": forbidden_hits,
        "minimumHits": minimum,
        "resultCount": result.total,
        "latencyMs": latency_ms,
    }
