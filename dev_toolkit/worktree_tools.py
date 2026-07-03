"""Git worktree boundary tools for the project toolkit MCP server."""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

TOOL_NAMES = {"worktree_guard"}


async def git_status_summary(run_command_json, repo_root: Path) -> dict[str, Any]:
    result = await run_command_json(
        ["git", "status", "--short", "--branch"],
        cwd=repo_root,
        timeout=10,
    )
    lines = [line for line in result.get("stdout", "").splitlines() if line.strip()]
    branch = lines[0].removeprefix("## ") if lines else ""
    changed = lines[1:]
    return {
        "branch": branch,
        "is_main": branch.split("...")[0] in {"main", "master"},
        "dirty_count": len(changed),
        "sample": changed[:25],
    }


async def git_changed_entries(run_command_json, repo_root: Path, include_untracked: bool = True) -> list[dict[str, str]]:
    cmd = ["git", "-c", "core.quotePath=false", "status", "--porcelain=v1"]
    if include_untracked:
        cmd.append("--untracked-files=all")
    result = await run_command_json(cmd, cwd=repo_root, timeout=10)
    entries: list[dict[str, str]] = []
    for line in result.get("stdout", "").splitlines():
        if not line.strip():
            continue
        status = line[:2]
        path = line[3:].strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        entries.append({"status": status, "path": path})
    return entries


def split_prefixes(raw: str) -> list[str]:
    return [item.strip().strip("/") for item in re.split(r"[,\n]", raw or "") if item.strip()]


def _extract_paths_from_list(items: list[Any]) -> list[str]:
    paths: list[str] = []
    for item in items:
        if isinstance(item, str):
            candidate = item.strip()
        elif isinstance(item, dict):
            candidate = str(item.get("path") or item.get("file") or item.get("name") or "").strip()
        else:
            candidate = ""
        if candidate:
            paths.append(candidate.strip("/"))
    return paths


def parse_baseline_paths(baseline_paths: str = "", baseline_status_json: str = "") -> set[str]:
    """Parse baseline paths from comma/newline text, JSON list, or prior guard JSON."""
    paths: list[str] = []
    raw_paths = (baseline_paths or "").strip()
    if raw_paths:
        try:
            decoded = json.loads(raw_paths)
        except json.JSONDecodeError:
            paths.extend(split_prefixes(raw_paths))
        else:
            if isinstance(decoded, list):
                paths.extend(_extract_paths_from_list(decoded))
            elif isinstance(decoded, dict):
                paths.extend(_extract_paths_from_status(decoded))

    raw_status = (baseline_status_json or "").strip()
    if raw_status:
        try:
            decoded = json.loads(raw_status)
        except json.JSONDecodeError:
            paths.extend(split_prefixes(raw_status))
        else:
            if isinstance(decoded, dict):
                paths.extend(_extract_paths_from_status(decoded))
            elif isinstance(decoded, list):
                paths.extend(_extract_paths_from_list(decoded))
    return {path for path in paths if path}


def _extract_paths_from_status(status: dict[str, Any]) -> list[str]:
    for key in ("changed_files", "paths", "changed", "entries", "dirty_files"):
        value = status.get(key)
        if isinstance(value, list):
            return _extract_paths_from_list(value)
    return []


def path_matches_prefix(path: str, prefix: str) -> bool:
    normalized = prefix.strip().strip("/")
    if not normalized:
        return False
    return path == normalized or path.startswith(normalized + "/")


def path_matches_forbidden(path: str, prefix: str) -> bool:
    normalized = prefix.strip().strip("/")
    if not normalized:
        return False
    if path_matches_prefix(path, normalized):
        return True
    if "/" not in normalized:
        return normalized in path.split("/")
    return False


def default_forbidden_prefixes() -> list[str]:
    return [
        ".git",
        "frontend/node_modules",
        "backend/.venv",
        "backend/venv",
        "__pycache__",
        "后端",
        "脚本",
        "部署",
        "backend/_废弃",
        "backend/脚本",
    ]


def group_changed_path(path: str) -> str:
    parts = path.split("/")
    if not parts:
        return "(unknown)"
    if parts[0] == "modules" and len(parts) > 1:
        return f"modules/{parts[1]}"
    if parts[0] in {"backend", "frontend", "dev_toolkit", "scripts", "开发文档"}:
        return "/".join(parts[:2]) if len(parts) > 1 else parts[0]
    return parts[0]


async def worktree_guard(
    run_command_json,
    repo_root: Path,
    module_key: str = "",
    allowed_prefixes: str = "",
    forbidden_prefixes: str = "",
    include_untracked: bool = True,
    baseline_paths: str = "",
    baseline_status_json: str = "",
) -> str:
    """Guard dirty worktree boundaries, including untracked files."""
    entries = await git_changed_entries(run_command_json, repo_root, include_untracked=include_untracked)
    paths = sorted({entry["path"] for entry in entries})
    baseline = parse_baseline_paths(baseline_paths, baseline_status_json)
    has_baseline = bool(baseline)
    allowed = split_prefixes(allowed_prefixes)
    if module_key and not allowed:
        allowed = [f"modules/{module_key}"]
    forbidden = default_forbidden_prefixes() + split_prefixes(forbidden_prefixes)

    outside_allowed = [
        path for path in paths
        if allowed and not any(path_matches_prefix(path, prefix) for prefix in allowed)
    ]
    forbidden_hits = [
        path for path in paths
        if any(path_matches_forbidden(path, prefix) for prefix in forbidden)
    ]
    new_since_baseline = [path for path in paths if path not in baseline]
    new_outside_allowed = [path for path in outside_allowed if path not in baseline]
    new_forbidden_hits = [path for path in forbidden_hits if path not in baseline]
    acknowledged_outside_changes = [path for path in outside_allowed if path in baseline]
    success = (
        not new_outside_allowed and not new_forbidden_hits
        if has_baseline
        else not outside_allowed and not forbidden_hits
    )

    by_group = Counter(group_changed_path(path) for path in paths)
    payload = {
        "success": success,
        "module_key": module_key,
        "allowed_prefixes": allowed,
        "forbidden_prefixes": forbidden,
        "include_untracked": include_untracked,
        "baseline_count": len(baseline),
        "changed_count": len(paths),
        "changed_files": paths[:200],
        "changed_by_group": dict(sorted(by_group.items())),
        "new_since_baseline_count": len(new_since_baseline),
        "new_since_baseline": new_since_baseline[:100],
        "outside_allowed_count": len(outside_allowed),
        "outside_allowed": outside_allowed[:100],
        "new_outside_allowed_count": len(new_outside_allowed),
        "new_outside_allowed": new_outside_allowed[:100],
        "acknowledged_outside_changes": acknowledged_outside_changes[:100],
        "forbidden_hit_count": len(forbidden_hits),
        "forbidden_hits": forbidden_hits[:100],
        "new_forbidden_hit_count": len(new_forbidden_hits),
        "new_forbidden_hits": new_forbidden_hits[:100],
        "hint": (
            "模块任务建议传 module_key；框架/全局任务可传 allowed_prefixes。"
            "本工具会包含 untracked 文件，比 git diff --name-only 更适合验收边界。"
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="worktree_guard",
            description="开工/收工边界守卫：汇总 dirty 文件(含 untracked)，按组归类，并校验 module_key/allowed_prefixes/forbidden_prefixes。",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_key": {"type": "string", "description": "模块 key；传入后默认只允许 modules/{module_key}/", "default": ""},
                    "allowed_prefixes": {"type": "string", "description": "逗号或换行分隔的允许路径前缀；为空则只做 forbidden 检查", "default": ""},
                    "forbidden_prefixes": {"type": "string", "description": "额外禁止路径前缀，逗号或换行分隔", "default": ""},
                    "include_untracked": {"type": "boolean", "description": "是否包含未跟踪文件", "default": True},
                    "baseline_paths": {"type": "string", "description": "开工基线 dirty 路径，支持逗号/换行或 JSON list；这些既有变更不判本轮失败", "default": ""},
                    "baseline_status_json": {"type": "string", "description": "开工时 worktree_guard/git status JSON；会从 changed_files/entries 等字段提取基线路径", "default": ""},
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(run_command_json, repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    if name == "worktree_guard":
        return await worktree_guard(
            run_command_json,
            repo_root,
            module_key=arguments.get("module_key", ""),
            allowed_prefixes=arguments.get("allowed_prefixes", ""),
            forbidden_prefixes=arguments.get("forbidden_prefixes", ""),
            include_untracked=bool(arguments.get("include_untracked", True)),
            baseline_paths=arguments.get("baseline_paths", ""),
            baseline_status_json=arguments.get("baseline_status_json", ""),
        )
    raise ValueError(f"未知工作区工具: {name}")
