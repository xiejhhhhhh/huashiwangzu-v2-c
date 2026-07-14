"""Tool usage telemetry component for the project toolkit MCP server."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_NAMES = {"tool_usage_stats"}

# Per-process trace ID — groups all calls from one MCP server session
_TRACE_ID: str = uuid.uuid4().hex[:16]
_SESSION_STARTED: str = datetime.now(timezone.utc).isoformat()


def empty_tool_usage() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "total_calls": 0,
        "tools": {},
        "categories": {},
        "recent_calls": [],
        "trace_id": _TRACE_ID,
        "session_started_at": _SESSION_STARTED,
    }


def read_tool_usage(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_tool_usage()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_tool_usage()
    if not isinstance(data, dict):
        return empty_tool_usage()
    # Schema migration: v1 -> v2
    if data.get("schema_version", 1) < 2:
        data.pop("agents", None)
        data.setdefault("categories", {})
        data.setdefault("trace_id", _TRACE_ID)
        data.setdefault("session_started_at", _SESSION_STARTED)
        for item in data.get("recent_calls", []):
            item.pop("agent", None)
            item.setdefault("category", "")
            item.setdefault("error_message", "")
            item.setdefault("trace_id", "")
        for item in data.get("tools", {}).values():
            item.setdefault("last_error", None)
        data["schema_version"] = 2
    data.setdefault("schema_version", 2)
    data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    data.setdefault("updated_at", None)
    data.setdefault("total_calls", 0)
    data.setdefault("tools", {})
    data.setdefault("categories", {})
    data.setdefault("recent_calls", [])
    data.setdefault("trace_id", _TRACE_ID)
    data.setdefault("session_started_at", _SESSION_STARTED)
    return data


def write_tool_usage(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def record_tool_usage(
    path: Path,
    name: str,
    success: bool,
    duration_seconds: float,
    arguments: dict[str, Any] | None = None,
    category: str = "",
    error_message: str = "",
) -> None:
    try:
        data = read_tool_usage(path)
        now = datetime.now(timezone.utc).isoformat()

        # ── Per-tool aggregation ──
        tools = data.setdefault("tools", {})
        item = tools.setdefault(
            name,
            {
                "calls": 0,
                "success": 0,
                "error": 0,
                "total_duration_seconds": 0.0,
                "last_called_at": None,
                "last_success": None,
                "last_error": None,
            },
        )
        item["calls"] = int(item.get("calls", 0)) + 1
        item["success" if success else "error"] = int(item.get("success" if success else "error", 0)) + 1
        item["total_duration_seconds"] = round(float(item.get("total_duration_seconds", 0.0)) + duration_seconds, 3)
        item["last_called_at"] = now
        item["last_success"] = success
        if not success and error_message:
            item["last_error"] = error_message[:500]

        # ── Per-category aggregation ──
        if category:
            cats = data.setdefault("categories", {})
            cat_item = cats.setdefault(category, {"calls": 0, "success": 0, "error": 0, "tools": {}})
            cat_item["calls"] = int(cat_item.get("calls", 0)) + 1
            cat_item["success" if success else "error"] = int(cat_item.get("success" if success else "error", 0)) + 1
            cat_tools = cat_item.setdefault("tools", {})
            cat_tools[name] = int(cat_tools.get(name, 0)) + 1

        # ── Recent calls (ring buffer, last 500) ──
        recent = data.setdefault("recent_calls", [])
        entry: dict[str, Any] = {
            "tool": name,
            "category": category,
            "success": success,
            "duration_seconds": round(duration_seconds, 3),
            "called_at": now,
            "trace_id": _TRACE_ID,
        }
        if not success and error_message:
            entry["error_message"] = error_message[:300]
        recent.append(entry)
        data["recent_calls"] = recent[-500:]
        data["total_calls"] = int(data.get("total_calls", 0)) + 1
        data["updated_at"] = now
        write_tool_usage(path, data)
    except Exception:
        # Usage telemetry must never break the actual development tool call.
        pass


async def tool_usage_stats(repo_root: Path, usage_path: Path, limit: int = 20, reset: bool = False, confirm: str = "") -> str:
    if reset:
        if confirm != "RESET":
            return json.dumps({"success": False, "error": "reset requires confirm='RESET'"}, ensure_ascii=False, indent=2)
        write_tool_usage(usage_path, empty_tool_usage())
    data = read_tool_usage(usage_path)
    tools = data.get("tools", {})

    # Rank tools by call count
    ranked = sorted(
        (
            {
                "tool": name,
                "calls": int(item.get("calls", 0)),
                "success": int(item.get("success", 0)),
                "error": int(item.get("error", 0)),
                "total_duration_seconds": float(item.get("total_duration_seconds", 0.0)),
                "avg_duration_seconds": round(
                    float(item.get("total_duration_seconds", 0.0)) / max(int(item.get("calls", 0)), 1), 3,
                ),
                "last_called_at": item.get("last_called_at"),
                "last_success": item.get("last_success"),
                "last_error": item.get("last_error"),
            }
            for name, item in tools.items()
        ),
        key=lambda item: (-item["calls"], item["tool"]),
    )

    # Top errors: aggregate by error message pattern
    recent = data.get("recent_calls", [])
    error_patterns: dict[str, int] = {}
    for r in recent:
        err = r.get("error_message", "")
        if err:
            # Group by first 80 chars
            pattern = err[:80]
            error_patterns[pattern] = error_patterns.get(pattern, 0) + 1

    top_errors = sorted(
        [{"pattern": k, "count": v} for k, v in error_patterns.items()],
        key=lambda x: -x["count"],
    )

    payload = {
        "success": True,
        "stats_path": str(usage_path.relative_to(repo_root)),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "total_calls": data.get("total_calls", 0),
        "trace_id": data.get("trace_id", ""),
        "session_started_at": data.get("session_started_at", ""),
        "top_tool": ranked[0] if ranked else None,
        "tools": ranked[: max(limit, 1)],
        "categories": data.get("categories", {}),
        "top_errors": top_errors[:10],
        "recent_failures": [r for r in recent[-50:] if not r.get("success")],
        "recent_calls": recent[-max(limit, 1):],
        "note": "category 按 handler 模块分组（core/code/edit/…），error_message 在失败时记录。trace_id 按 MCP 进程生命周期生成，同一次连接内的调用共享同一 trace_id。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="tool_usage_stats",
            description="统计项目工具台 MCP 工具调用热度，返回调用最多的工具、成功/失败次数、平均耗时、错误模式分析和调用链追踪信息。可 confirm=RESET 重置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "返回前 N 个工具", "default": 20},
                    "reset": {"type": "boolean", "description": "是否重置统计", "default": False},
                    "confirm": {"type": "string", "description": "reset=true 时必须传 RESET", "default": ""},
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, usage_path: Path, name: str, arguments: dict[str, Any]) -> str:
    if name == "tool_usage_stats":
        return await tool_usage_stats(
            repo_root,
            usage_path,
            limit=int(arguments.get("limit", 20)),
            reset=bool(arguments.get("reset", False)),
            confirm=arguments.get("confirm", ""),
        )
    raise ValueError(f"未知工具统计工具: {name}")
