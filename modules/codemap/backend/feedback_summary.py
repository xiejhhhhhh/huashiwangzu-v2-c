"""Feedback visibility helpers for codemap stats and list responses."""

from __future__ import annotations

NO_FEEDBACK_NOTE = "暂无 codemap_feedback 反馈样本，empirical_accuracy 未知，不能视为 100% 准确。"
FEEDBACK_WITHOUT_QUERY_NOTE = "已有不准反馈，但 query_count 为 0；先按 0% 处理并检查计数链路。"


def build_empirical_accuracy_fields(query_count: int, feedback_count: int) -> dict:
    """Return explicit empirical accuracy fields without pretending no feedback means 100%."""
    safe_query_count = max(int(query_count or 0), 0)
    safe_feedback_count = max(int(feedback_count or 0), 0)

    if safe_feedback_count == 0:
        return {
            "empirical_accuracy": None,
            "empirical_accuracy_status": "no_feedback",
            "empirical_accuracy_note": NO_FEEDBACK_NOTE,
        }

    if safe_query_count == 0:
        return {
            "empirical_accuracy": 0,
            "empirical_accuracy_status": "feedback_without_query_count",
            "empirical_accuracy_note": FEEDBACK_WITHOUT_QUERY_NOTE,
        }

    accuracy = max(0, 100 - int(safe_feedback_count * 100 / safe_query_count))
    return {
        "empirical_accuracy": accuracy,
        "empirical_accuracy_status": "measured",
        "empirical_accuracy_note": None,
    }


def build_feedback_list_metadata(
    *,
    feedback_count: int,
    page: int,
    page_size: int,
    aggregated_by_path: bool,
    path: str | None = None,
    path_count: int | None = None,
) -> dict:
    """Common metadata for list_feedback, including a visible empty state."""
    safe_feedback_count = max(int(feedback_count or 0), 0)
    metadata = {
        "feedback_count": safe_feedback_count,
        "has_feedback": safe_feedback_count > 0,
        "page": max(int(page or 1), 1),
        "page_size": max(int(page_size or 50), 1),
        "aggregated_by_path": aggregated_by_path,
    }
    if path is not None:
        metadata["path"] = path
    if path_count is not None:
        metadata["path_count"] = max(int(path_count or 0), 0)
    if safe_feedback_count == 0:
        metadata["empty_note"] = NO_FEEDBACK_NOTE
    return metadata
