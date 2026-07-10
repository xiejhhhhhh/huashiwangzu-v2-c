"""Read-only bug log inspection tools for the project toolkit."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_NAMES = {"bug_logs", "bug_log_files"}

_MAX_TAIL_BYTES = 2 * 1024 * 1024
_DEFAULT_LINES = 500
_MAX_LINES = 5000
_DEFAULT_LIMIT = 30
_MAX_LIMIT = 200

_CRITICAL_RE = re.compile(r"\b(critical|fatal|panic)\b", re.IGNORECASE)
_ERROR_RE = re.compile(
    r"(traceback|exception|\berror\b|internal server error|xhr 加载失败|网络异常|failed|failure|\b5\d\d\b)",
    re.IGNORECASE,
)
_WARNING_RE = re.compile(r"(\bwarn(?:ing)?\b|degraded|timeout|timed out|\b40[13]\b|retry)", re.IGNORECASE)


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _normalise_sources(value: Any) -> set[str]:
    if value in (None, "", "all"):
        return {"all"}
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = [str(value).strip()]
    sources = {item for item in raw_items if item}
    return sources or {"all"}


def _source_for_path(log_root: Path, path: Path) -> str:
    relative = path.relative_to(log_root)
    parts = relative.parts
    name = path.name
    lowered = str(relative).lower()
    if "frontend" in lowered or name == "request.log":
        return "frontend"
    if parts and parts[0] == "modules":
        return parts[1].removesuffix(".log") if len(parts) > 1 else "modules"
    if parts and parts[0] in {"tool-jobs", "opencode-dispatches", "opencode-pty"}:
        return "toolkit"
    if "watchdog" in lowered:
        return "watchdog"
    if "worker" in lowered or "task_queue" in lowered or "knowledge_bulk" in lowered:
        return "worker"
    return "backend"


def _wanted_source(source: str, path: Path, requested: set[str], module: str) -> bool:
    if module:
        return path.name == f"{module}.log" or f"/{module}." in str(path)
    if "all" in requested:
        return True
    if source in requested:
        return True
    if source not in {"backend", "frontend", "watchdog", "worker", "toolkit"} and "modules" in requested:
        return True
    return False


def _iter_log_files(repo_root: Path, *, sources: set[str], module: str, include_archived: bool) -> list[dict[str, Any]]:
    log_root = repo_root / "backend" / "logs"
    if not log_root.exists():
        return []

    patterns = ["*.log", "modules/*.log", "tool-jobs/*.log", "opencode-dispatches/*.log", "opencode-pty/*.log"]
    if include_archived:
        patterns.extend(["*.log.*", "modules/*.log.*"])

    seen: set[Path] = set()
    items: list[dict[str, Any]] = []
    for pattern in patterns:
        for path in log_root.glob(pattern):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            stat = path.stat()
            source = _source_for_path(log_root, path)
            if not _wanted_source(source, path, sources, module):
                continue
            items.append(
                {
                    "path": path,
                    "source": source,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
    return sorted(items, key=lambda item: item["path"].stat().st_mtime, reverse=True)


def _tail_lines(path: Path, line_limit: int) -> list[str]:
    size = path.stat().st_size
    if size == 0:
        return []
    with path.open("rb") as handle:
        handle.seek(max(0, size - _MAX_TAIL_BYTES))
        data = handle.read()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-line_limit:]


def _detect_severity(line: str) -> str:
    if _CRITICAL_RE.search(line):
        return "critical"
    if _ERROR_RE.search(line):
        return "error"
    if _WARNING_RE.search(line):
        return "warning"
    return "info"


def _severity_matches(line_severity: str, requested: str, has_query: bool) -> bool:
    if requested == "all":
        return has_query or line_severity != "info"
    if requested == "warning":
        return line_severity in {"critical", "error", "warning"}
    return line_severity in {"critical", "error"}


def _context(lines: list[str], index: int, context_lines: int) -> list[str]:
    if context_lines <= 0:
        return []
    start = max(0, index - context_lines)
    end = min(len(lines), index + context_lines + 1)
    return [line[:800] for line in lines[start:end] if line]


def bug_log_files(
    repo_root: Path,
    *,
    sources: Any = "all",
    module: str = "",
    include_archived: bool = False,
    include_empty: bool = False,
) -> dict[str, Any]:
    requested_sources = _normalise_sources(sources)
    files = _iter_log_files(repo_root, sources=requested_sources, module=module.strip(), include_archived=include_archived)
    visible = [
        {
            "source": item["source"],
            "path": str(item["path"].relative_to(repo_root)),
            "size_bytes": item["size_bytes"],
            "modified_at": item["modified_at"],
        }
        for item in files
        if include_empty or item["size_bytes"] > 0
    ]
    return {
        "success": True,
        "filters": {
            "sources": sorted(requested_sources),
            "module": module.strip(),
            "include_archived": include_archived,
            "include_empty": include_empty,
        },
        "file_count": len(visible),
        "files": visible,
    }


def bug_logs(
    repo_root: Path,
    *,
    query: str = "",
    severity: str = "error",
    sources: Any = "all",
    module: str = "",
    lines: int = _DEFAULT_LINES,
    limit: int = _DEFAULT_LIMIT,
    context_lines: int = 1,
    include_archived: bool = False,
) -> dict[str, Any]:
    requested_sources = _normalise_sources(sources)
    severity_filter = severity if severity in {"error", "warning", "all"} else "error"
    line_limit = _clamp_int(lines, _DEFAULT_LINES, 1, _MAX_LINES)
    match_limit = _clamp_int(limit, _DEFAULT_LIMIT, 1, _MAX_LIMIT)
    context_limit = _clamp_int(context_lines, 1, 0, 5)
    query_text = query.strip()
    query_lower = query_text.lower()

    files = _iter_log_files(repo_root, sources=requested_sources, module=module.strip(), include_archived=include_archived)
    matches: list[dict[str, Any]] = []
    summary: dict[str, dict[str, int]] = {}
    skipped: list[dict[str, str]] = []

    for item in files:
        path = item["path"]
        relative_path = str(path.relative_to(repo_root))
        file_summary = summary.setdefault(relative_path, {"critical": 0, "error": 0, "warning": 0})
        try:
            tail = _tail_lines(path, line_limit)
        except OSError as exc:
            skipped.append({"path": relative_path, "reason": str(exc)})
            continue

        for index in range(len(tail) - 1, -1, -1):
            line = tail[index]
            if query_lower and query_lower not in line.lower():
                continue
            detected = _detect_severity(line)
            if detected in file_summary:
                file_summary[detected] += 1
            if not _severity_matches(detected, severity_filter, bool(query_lower)):
                continue
            matches.append(
                {
                    "source": item["source"],
                    "path": relative_path,
                    "severity": detected,
                    "tail_line_index": index + 1,
                    "message": line[:1000],
                    "context": _context(tail, index, context_limit),
                }
            )
            if len(matches) >= match_limit:
                break
        if len(matches) >= match_limit:
            break

    return {
        "success": True,
        "filters": {
            "query": query_text,
            "severity": severity_filter,
            "sources": sorted(requested_sources),
            "module": module.strip(),
            "lines_per_file": line_limit,
            "limit": match_limit,
            "context_lines": context_limit,
            "include_archived": include_archived,
        },
        "scanned_files": len(files),
        "skipped_files": skipped,
        "summary": summary,
        "matches": matches,
        "next_steps": [
            "加 query 精确过滤报错关键词、接口路径或模块名。",
            "用 module=knowledge/agent 等聚焦单个模块日志。",
            "需要原始尾部时再用 tail_log(module, lines)。",
        ],
    }


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    log_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "可选关键词，匹配接口、异常名、模块名或报错文本", "default": ""},
            "severity": {
                "type": "string",
                "description": "过滤级别：error / warning / all",
                "enum": ["error", "warning", "all"],
                "default": "error",
            },
            "sources": {
                "description": "日志来源：all/backend/modules/frontend/worker/watchdog/toolkit，可传数组或逗号字符串",
                "default": "all",
            },
            "module": {"type": "string", "description": "可选模块名，如 knowledge、agent", "default": ""},
            "lines": {"type": "number", "description": "每个文件只读尾部多少行，上限 5000", "default": _DEFAULT_LINES},
            "limit": {"type": "number", "description": "最多返回多少条匹配，上限 200", "default": _DEFAULT_LIMIT},
            "context_lines": {"type": "number", "description": "每条匹配附带上下文行数，上限 5", "default": 1},
            "include_archived": {"type": "boolean", "description": "是否包含 .log.1 等轮转日志", "default": False},
        },
    }
    files_schema = {
        "type": "object",
        "properties": {
            "sources": {
                "description": "日志来源：all/backend/modules/frontend/worker/watchdog/toolkit，可传数组或逗号字符串",
                "default": "all",
            },
            "module": {"type": "string", "description": "可选模块名，如 knowledge、agent", "default": ""},
            "include_archived": {"type": "boolean", "description": "是否包含 .log.1 等轮转日志", "default": False},
            "include_empty": {"type": "boolean", "description": "是否显示空日志文件", "default": False},
        },
    }
    return [
        Tool(
            name="bug_logs",
            description="只读汇总最近 bug 线索：错误、异常、Traceback、前端网络异常、job 失败；用于先定位再细查。",
            inputSchema=log_schema,
        ),
        Tool(
            name="bug_log_files",
            description="列出项目日志文件、来源、大小和更新时间，方便选择要查的模块或来源。",
            inputSchema=files_schema,
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    if name == "bug_logs":
        return json.dumps(
            bug_logs(
                repo_root,
                query=arguments.get("query", ""),
                severity=arguments.get("severity", "error"),
                sources=arguments.get("sources", "all"),
                module=arguments.get("module", ""),
                lines=arguments.get("lines", _DEFAULT_LINES),
                limit=arguments.get("limit", _DEFAULT_LIMIT),
                context_lines=arguments.get("context_lines", 1),
                include_archived=bool(arguments.get("include_archived", False)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "bug_log_files":
        return json.dumps(
            bug_log_files(
                repo_root,
                sources=arguments.get("sources", "all"),
                module=arguments.get("module", ""),
                include_archived=bool(arguments.get("include_archived", False)),
                include_empty=bool(arguments.get("include_empty", False)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    raise ValueError(f"未知日志工具: {name}")
