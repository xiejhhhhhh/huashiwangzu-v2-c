"""HTTP/capability parameter helpers for pipeline debt governance."""
from __future__ import annotations

import json
from typing import Any

from app.database import AsyncSessionLocal

from .document_service import resolve_user_id
from .pipeline_debt_service import (
    apply_pipeline_lifecycle_debt_action,
    classify_pipeline_lifecycle_debt,
    reconcile_pending_pipeline_queue,
    reconcile_running_pipeline_queue,
)


def merge_category_params(category: str | None, categories: list[str] | None) -> list[str]:
    merged: list[str] = []
    for raw in ([category] if category else []) + list(categories or []):
        for part in str(raw).split(","):
            value = part.strip()
            if value and value not in merged:
                merged.append(value)
    return merged


def parse_category_limits_query(raw: str | None) -> dict[str, int]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
        for token in raw.split(","):
            if ":" not in token:
                continue
            key, value = token.split(":", 1)
            try:
                parsed[key.strip()] = int(value.strip())
            except ValueError:
                continue
    if not isinstance(parsed, dict):
        return {}
    return normalize_category_limits_payload(parsed)


def normalize_category_limits_payload(raw: dict[str, Any] | None) -> dict[str, int]:
    limits: dict[str, int] = {}
    for key, value in (raw or {}).items():
        try:
            limit = int(value)
        except (TypeError, ValueError):
            continue
        if key and limit > 0:
            limits[str(key)] = limit
    return limits


def _coerce_int_list(raw: Any) -> list[int]:
    if not isinstance(raw, list):
        return []
    values: list[int] = []
    for item in raw:
        try:
            values.append(int(item))
        except (TypeError, ValueError):
            continue
    return values


def _coerce_limit_each(raw: Any) -> int | None:
    if not raw:
        return None
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return None
    return limit if limit > 0 else None


def _normalize_order(raw: Any) -> str:
    order = str(raw or "newest")
    return order if order in {"newest", "oldest"} else "newest"


async def cap_classify_pipeline_debt(params: dict, caller: str) -> dict:
    resolve_user_id(caller)
    limit = max(1, min(int(params.get("limit", 500) or 500), 5000))
    category = params.get("category")
    categories = params.get("categories") if isinstance(params.get("categories"), list) else []
    async with AsyncSessionLocal() as db:
        return await classify_pipeline_lifecycle_debt(
            db,
            limit=limit,
            task_ids=_coerce_int_list(params.get("task_ids")) or None,
            categories=merge_category_params(str(category) if category else None, categories),
            category_limits=normalize_category_limits_payload(
                params.get("category_limits") if isinstance(params.get("category_limits"), dict) else {}
            ),
            limit_each=_coerce_limit_each(params.get("limit_each")),
            order=_normalize_order(params.get("order")),
        )


async def cap_apply_pipeline_debt(params: dict, caller: str) -> dict:
    resolve_user_id(caller)
    category = params.get("category")
    categories = params.get("categories") if isinstance(params.get("categories"), list) else []
    async with AsyncSessionLocal() as db:
        return await apply_pipeline_lifecycle_debt_action(
            db,
            action=str(params.get("action") or ""),
            limit=max(1, min(int(params.get("limit", 500) or 500), 5000)),
            task_ids=_coerce_int_list(params.get("task_ids")) or None,
            dry_run=bool(params.get("dry_run", True)),
            categories=merge_category_params(str(category) if category else None, categories),
            category_limits=normalize_category_limits_payload(
                params.get("category_limits") if isinstance(params.get("category_limits"), dict) else {}
            ),
            limit_each=_coerce_limit_each(params.get("limit_each")),
            order=_normalize_order(params.get("order")),
        )


async def cap_reconcile_pending_pipeline_queue(params: dict, caller: str) -> dict:
    resolve_user_id(caller)
    category = params.get("category")
    categories = params.get("categories") if isinstance(params.get("categories"), list) else []
    async with AsyncSessionLocal() as db:
        return await reconcile_pending_pipeline_queue(
            db,
            limit=max(1, min(int(params.get("limit", 500) or 500), 5000)),
            task_ids=_coerce_int_list(params.get("task_ids")) or None,
            dry_run=bool(params.get("dry_run", True)),
            categories=merge_category_params(str(category) if category else None, categories),
            category_limits=normalize_category_limits_payload(
                params.get("category_limits") if isinstance(params.get("category_limits"), dict) else {}
            ),
            limit_each=_coerce_limit_each(params.get("limit_each")),
            order=_normalize_order(params.get("order")),
        )


async def cap_reconcile_running_pipeline_queue(params: dict, caller: str) -> dict:
    resolve_user_id(caller)
    category = params.get("category")
    categories = params.get("categories") if isinstance(params.get("categories"), list) else []
    async with AsyncSessionLocal() as db:
        return await reconcile_running_pipeline_queue(
            db,
            limit=max(1, min(int(params.get("limit", 500) or 500), 5000)),
            task_ids=_coerce_int_list(params.get("task_ids")) or None,
            dry_run=bool(params.get("dry_run", True)),
            categories=merge_category_params(str(category) if category else None, categories),
            category_limits=normalize_category_limits_payload(
                params.get("category_limits") if isinstance(params.get("category_limits"), dict) else {}
            ),
            limit_each=_coerce_limit_each(params.get("limit_each")),
            order=_normalize_order(params.get("order")),
        )
