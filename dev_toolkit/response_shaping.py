"""Response shaping helpers for MCP probe-style tool outputs."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResponseShapeOptions:
    selector: str | None = None
    max_items: int | None = None
    max_bytes: int | None = None


def shape_response(payload: dict[str, Any], options: ResponseShapeOptions | None = None) -> dict[str, Any]:
    """Return a backward-compatible or trimmed response payload."""
    if options is None or not _has_limits(options):
        return payload

    warnings: list[str] = []
    omitted_counts: dict[str, int] = {}
    selected_path: str | None = None
    shaped = copy.deepcopy(payload)

    selector = (options.selector or "").strip()
    if selector:
        resolved, selected, warning = _select_path(payload, selector)
        if warning:
            warnings.append(warning)
        else:
            selected_path = resolved
            shaped = _selected_payload(payload, selected)

    if options.max_items is not None:
        max_items = max(0, int(options.max_items))
        shaped = _trim_lists(shaped, max_items, omitted_counts, selected_path)

    meta = {
        "truncated": bool(omitted_counts),
        "selected_path": selected_path,
        "omitted_counts": omitted_counts,
    }
    if warnings:
        meta["warnings"] = warnings
    shaped["response_meta"] = meta

    if options.max_bytes is not None:
        shaped = _trim_to_max_bytes(shaped, max(0, int(options.max_bytes)))
    return shaped


def dumps_response(payload: dict[str, Any], options: ResponseShapeOptions | None = None) -> str:
    shaped = shape_response(payload, options)
    return json.dumps(shaped, ensure_ascii=False, indent=2)


def _has_limits(options: ResponseShapeOptions) -> bool:
    return bool(options.selector) or options.max_items is not None or options.max_bytes is not None


def _select_path(payload: Any, selector: str) -> tuple[str | None, Any, str | None]:
    current = payload
    parts = [part for part in selector.split(".") if part]
    if not parts:
        return None, None, "selector is empty"

    traversed: list[str] = []
    for part in parts:
        traversed.append(part)
        if isinstance(current, dict):
            if part not in current:
                return None, None, f"selector not found at {'.'.join(traversed)}"
            current = current[part]
            continue
        if isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                return None, None, f"selector expected list index at {'.'.join(traversed)}"
            if index < 0 or index >= len(current):
                return None, None, f"selector index out of range at {'.'.join(traversed)}"
            current = current[index]
            continue
        return None, None, f"selector cannot traverse scalar at {'.'.join(traversed)}"
    return ".".join(parts), current, None


def _selected_payload(payload: dict[str, Any], selected: Any) -> dict[str, Any]:
    shaped: dict[str, Any] = {}
    for key in ("status_code", "status", "success", "error", "target"):
        if key in payload:
            shaped[key] = copy.deepcopy(payload[key])
    if isinstance(payload.get("data"), dict):
        envelope = payload["data"]
        if "success" in envelope:
            shaped["upstream_success"] = envelope["success"]
        if "error" in envelope:
            shaped["upstream_error"] = copy.deepcopy(envelope["error"])
    shaped["data"] = copy.deepcopy(selected)
    return shaped


def _trim_lists(
    value: Any,
    max_items: int,
    omitted_counts: dict[str, int],
    selected_path: str | None,
    path: str = "",
) -> Any:
    if isinstance(value, list):
        omitted = max(0, len(value) - max_items)
        if omitted:
            count_path = selected_path if path == "data" and selected_path else path or "$"
            omitted_counts[count_path] = omitted
        return [
            _trim_lists(item, max_items, omitted_counts, selected_path, _join_path(path, str(index)))
            for index, item in enumerate(value[:max_items])
        ]
    if isinstance(value, dict):
        return {
            key: _trim_lists(item, max_items, omitted_counts, selected_path, _join_path(path, key))
            for key, item in value.items()
        }
    return value


def _trim_to_max_bytes(payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    if _json_size(payload) <= max_bytes:
        return payload

    shaped = copy.deepcopy(payload)
    meta = shaped.setdefault("response_meta", {})
    meta["truncated"] = True
    meta["max_bytes"] = max_bytes
    meta["bytes_before"] = _json_size(payload)
    shaped["data"] = _summarize_value(shaped.get("data"), max_bytes)
    if _json_size(shaped) <= max_bytes:
        return shaped

    shaped["data"] = {
        "_truncated": True,
        "type": type(payload.get("data")).__name__,
        "bytes_before": _json_size(payload.get("data")),
    }
    if _json_size(shaped) <= max_bytes:
        return shaped

    meta["warnings"] = [*meta.get("warnings", []), "minimum response exceeds max_bytes"]
    return shaped


def _summarize_value(value: Any, max_bytes: int) -> Any:
    if isinstance(value, str):
        return {
            "_truncated": True,
            "type": "str",
            "bytes_before": _json_size(value),
            "preview": value[: max(0, min(len(value), max_bytes // 4))],
        }
    if isinstance(value, list):
        return {
            "_truncated": True,
            "type": "list",
            "original_length": len(value),
            "preview": [_summarize_value(item, max_bytes // 2) for item in value[:3]],
        }
    if isinstance(value, dict):
        preview: dict[str, Any] = {}
        for key, item in list(value.items())[:8]:
            if isinstance(item, str | int | float | bool) or item is None:
                preview[key] = item
            else:
                preview[key] = _summarize_value(item, max_bytes // 2)
        return {
            "_truncated": True,
            "type": "dict",
            "keys": list(value.keys())[:20],
            "preview": preview,
            "bytes_before": _json_size(value),
        }
    return value


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def _join_path(base: str, key: str) -> str:
    return f"{base}.{key}" if base else key
