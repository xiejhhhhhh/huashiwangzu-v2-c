"""Validation helpers for codemap public inputs."""

from __future__ import annotations

from .graph.graph import normalize_path


def normalize_required_path(path: object) -> str:
    raw_path = str(path or "").strip()
    if not raw_path:
        raise ValueError("path is required")
    normalized = normalize_path(raw_path)
    if (
        normalized in ("", ".", "..")
        or normalized.startswith("../")
        or normalized.startswith("/")
        or "/../" in f"/{normalized}/"
    ):
        raise ValueError("path must be inside repository root")
    return normalized


def validate_feedback_fields(path: object, query_type: object) -> tuple[str, str]:
    normalized_path = normalize_required_path(path)
    normalized_query_type = str(query_type or "").strip()
    if not normalized_query_type:
        raise ValueError("query_type is required")
    if len(normalized_query_type) > 32:
        raise ValueError("query_type must be at most 32 characters")
    return normalized_path, normalized_query_type
