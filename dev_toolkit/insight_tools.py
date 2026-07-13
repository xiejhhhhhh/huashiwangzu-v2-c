"""Insight and self-check tools for the project toolkit MCP server."""

from __future__ import annotations

import importlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from dev_toolkit.mcp_entry import validate_declared_server_config
    from dev_toolkit.tool_usage_tools import read_tool_usage
except ModuleNotFoundError:
    from mcp_entry import validate_declared_server_config
    from tool_usage_tools import read_tool_usage

TOOL_NAMES = {"mcp_self_check", "dev_toolkit_architecture_audit", "agent_activity_report"}
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
NONSTANDARD_COMPONENT_FILES = ("docs_sync.py",)


def _repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return 0


def _parse_frontmatter(text: str) -> dict[str, Any]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    data: dict[str, Any] = {}
    for raw_line in match.group(1).splitlines():
        if ":" not in raw_line:
            continue
        key, raw_value = raw_line.split(":", 1)
        value = raw_value.strip().strip('"')
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip().strip('"') for item in value[1:-1].split(",") if item.strip()]
            data[key.strip()] = items
        else:
            data[key.strip()] = value
    return data


def _section(text: str, title: str) -> str:
    pattern = re.compile(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _feedback_rating(text: str) -> int | None:
    match = re.search(r"评分[:：]\s*(\d+)", text)
    return int(match.group(1)) if match else None


def _memory_files(repo_root: Path) -> list[Path]:
    memory_dir = repo_root / "开发文档" / "项目记忆"
    if not memory_dir.exists():
        return []
    return sorted(path for path in memory_dir.glob("*.md") if path.is_file() and not path.name.startswith("_"))


def _load_memories(repo_root: Path, limit: int = 200) -> list[dict[str, Any]]:
    items = []
    for path in sorted(_memory_files(repo_root), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta = _parse_frontmatter(text)
        items.append({"path": _repo_rel(repo_root, path), "meta": meta, "text": text})
    return items


def _component_tool_names(module_name: str) -> list[str]:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        module = importlib.import_module(module_name.rsplit(".", 1)[-1])
    if not hasattr(module, "tool_definitions"):
        return []
    try:
        return [tool.name for tool in module.tool_definitions()]
    except Exception:
        return []


def _discover_components(repo_root: Path) -> list[dict[str, Any]]:
    components = []
    component_paths = set((repo_root / "dev_toolkit").glob("*_tools.py"))
    component_paths.update(repo_root / "dev_toolkit" / name for name in NONSTANDARD_COMPONENT_FILES)
    for path in sorted(component_paths):
        if not path.is_file():
            continue
        if path.name.startswith("test_"):
            continue
        module_stem = path.stem
        module_name = f"dev_toolkit.{module_stem}"
        text = path.read_text(encoding="utf-8")
        tool_names = _component_tool_names(module_name)
        components.append(
            {
                "file": _repo_rel(repo_root, path),
                "module": module_name,
                "lines": len(text.splitlines()),
                "has_tool_definitions": "def tool_definitions" in text,
                "has_handles_tool": "def handles_tool" in text,
                "has_handle_tool": "def handle_tool" in text,
                "tools": tool_names,
            }
        )
    return components


def _wired_component_tools(server_path: Path) -> list[dict[str, Any]]:
    """Parse server.py to determine which component tools are actually wired.

    Reads the per-alias import lines (e.g. each ``from dev_toolkit.code_tools import tool_definitions as code_tool_definitions``),
    the ``*X()`` call in ``list_tools``, and the ``elif X_handles_tool(name)`` chain in ``call_tool``.
    """
    try:
        text = server_path.read_text(encoding="utf-8")
    except OSError:
        return []

    # Collect import aliases: component -> {defs_alias, handles_alias}
    # Only include modules that export the component contract (tool_definitions + handles_tool)
    aliases: dict[str, dict[str, str | None]] = {}
    for m in re.finditer(
        r"from dev_toolkit\.(\w+) import (\w+) as (\w+)",
        text,
    ):
        component = m.group(1)
        symbol = m.group(2)
        alias = m.group(3)
        entry = aliases.setdefault(component, {"defs_alias": None, "handles_alias": None})
        if symbol == "tool_definitions":
            entry["defs_alias"] = alias
        elif symbol == "handles_tool":
            entry["handles_alias"] = alias

    # Drop imports that don't export both tool_definitions and handles_tool (helpers, not components)
    aliases = {k: v for k, v in aliases.items() if v["defs_alias"] and v["handles_alias"]}

    # Imports in list_tools: *core_tool_definitions()
    registered_in_list = set()
    for m in re.finditer(r"\*(\w+)\(\)", text):
        registered_in_list.add(m.group(1))

    # Dispatch branches in call_tool: if/elif X_handles_tool(name)
    dispatched = set()
    for m in re.finditer(r"(?:if|elif) (\w+)\(name\):", text):
        dispatched.add(m.group(1))

    wired = []
    for component, entry in sorted(aliases.items()):
        defs_alias = entry["defs_alias"]
        handles_alias = entry["handles_alias"]
        registered = defs_alias in registered_in_list if defs_alias else False
        dispatched_flag = handles_alias in dispatched if handles_alias else False
        wired.append({
            "component": component,
            "imported": True,
            "registered_in_list_tools": registered,
            "dispatched_in_call_tool": dispatched_flag,
            "wired": registered and dispatched_flag,
            "issue": "" if (registered and dispatched_flag)
            else "missing from list_tools" if not registered
            else "missing dispatch in call_tool",
        })
    return wired


def _orphan_component_tools(components: list[dict[str, Any]], wired: list[dict[str, Any]]) -> list[str]:
    """Tools declared in component files but whose component is not fully wired in server.py."""
    wired_components = {w["component"] for w in wired if w["wired"]}
    orphan_tools = []
    for comp in components:
        module = comp.get("module", "")
        stem = module.split(".")[-1] if "." in module else module
        if stem not in wired_components:
            orphan_tools.extend(comp.get("tools", []))
    return sorted(orphan_tools)


def mcp_self_check(repo_root: Path, usage_path: Path, include_tools: bool = True) -> str:
    components = _discover_components(repo_root)
    server_path = repo_root / "dev_toolkit" / "server.py"
    entrypoint = validate_declared_server_config(repo_root)
    wired = _wired_component_tools(server_path)
    component_tools = [tool for component in components for tool in component["tools"]]
    orphan_tools = _orphan_component_tools(components, wired)
    duplicates = sorted(name for name, count in Counter(component_tools).items() if count > 1)
    long_files = [
        {"path": _repo_rel(repo_root, path), "lines": _line_count(path)}
        for path in sorted((repo_root / "dev_toolkit").glob("*.py"))
        if _line_count(path) > 600
    ]
    usage = read_tool_usage(usage_path)
    warnings = []
    if not entrypoint.get("success", False):
        warnings.append(".mcp.json does not match dev_toolkit/mcp_entry.py expected stdio declaration.")
    if _line_count(server_path) > 600:
        warnings.append("dev_toolkit/server.py is still larger than 600 lines; keep migrating tool groups into *_tools.py components.")
    if duplicates:
        warnings.append("Duplicate tool names found: " + ", ".join(duplicates))
    for w in wired:
        if not w["wired"]:
            warnings.append(
                f"dev_toolkit/{w['component']}.py is not fully wired: {w['issue']}"
            )
    if orphan_tools:
        warnings.append(
            f"Tools declared in component files but NOT fully wired in server.py "
            f"(orphan, will 404 at runtime): {', '.join(orphan_tools)}"
        )
    fully_wired = all(item.get("wired") for item in wired)
    payload = {
        "success": bool(entrypoint.get("success", False)) and fully_wired and not duplicates and not orphan_tools,
        "server": {"path": _repo_rel(repo_root, server_path), "lines": _line_count(server_path)},
        "entrypoint": entrypoint,
        "component_count": len(components),
        "components": components,
        "wired_components": wired,
        "direct_tool_count": 0,
        "component_tool_count": len(component_tools),
        "total_declared_tools": len(sorted(set(component_tools))),
        "duplicate_tools": duplicates,
        "orphan_tools": orphan_tools,
        "long_files": long_files,
        "usage_total_calls": usage.get("total_calls", 0),
        "delayed_loading_hint": "Codex may expose only a subset of MCP tools until tool_search loads matching names or descriptions.",
        "warnings": warnings,
    }
    if include_tools:
        payload["tools"] = sorted(set(component_tools))
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _summarize_feedback(memories: list[dict[str, Any]]) -> dict[str, Any]:
    by_agent: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "memory_count": 0,
            "feedback_count": 0,
            "ratings": [],
            "declared_tools": Counter(),
            "friction": [],
            "missing_tools": [],
            "upgrade_suggestions": [],
            "latest_items": [],
        }
    )
    for item in memories:
        meta = item["meta"]
        agent = str(meta.get("agent") or "unknown")
        bucket = by_agent[agent]
        bucket["memory_count"] += 1
        bucket["latest_items"].append({"path": item["path"], "name": meta.get("name", ""), "created": meta.get("created", "")})
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        if "mcp-feedback" not in tags:
            continue
        text = item["text"]
        bucket["feedback_count"] += 1
        rating = _feedback_rating(text)
        if rating is not None:
            bucket["ratings"].append(rating)
        for tool in re.split(r"[,\n]", _section(text, "本次用到的工具")):
            tool = tool.strip().strip("`")
            if tool:
                bucket["declared_tools"][tool] += 1
        for field, title in (
            ("friction", "卡点 / 不顺手的地方"),
            ("missing_tools", "缺少的工具 / 能力"),
            ("upgrade_suggestions", "升级建议"),
        ):
            value = _section(text, title)
            if value:
                bucket[field].append(value[:500])
    summary = {}
    for agent, bucket in by_agent.items():
        ratings = bucket.pop("ratings")
        declared_tools = bucket.pop("declared_tools")
        summary[agent] = {
            **bucket,
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "declared_tools": declared_tools.most_common(20),
            "latest_items": bucket["latest_items"][:10],
        }
    return summary


def _mailbox_report(repo_root: Path) -> dict[str, Any]:
    root = repo_root.parent / "华世王镞_v2邮箱"
    if not root.exists():
        return {"exists": False, "root": str(root)}
    meta_files = sorted(root.glob("**/元信息.json"))
    by_agent = Counter()
    statuses = Counter()
    samples = []
    for path in meta_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        agent = str(data.get("agent") or data.get("author") or data.get("执行agent") or data.get("执行者") or "unknown")
        status = str(data.get("status") or data.get("状态") or "unknown")
        by_agent[agent] += 1
        statuses[status] += 1
        if len(samples) < 20:
            samples.append({"path": _repo_rel(root, path), "agent": agent, "status": status})
    return {
        "exists": True,
        "root": str(root),
        "meta_file_count": len(meta_files),
        "by_agent": dict(by_agent.most_common()),
        "statuses": dict(statuses.most_common()),
        "samples": samples,
    }


def agent_activity_report(repo_root: Path, usage_path: Path, agent: str = "", limit: int = 200) -> str:
    memories = _load_memories(repo_root, limit=max(limit, 1))
    feedback_summary = _summarize_feedback(memories)
    if agent:
        feedback_summary = {agent: feedback_summary.get(agent, {})}
    usage = read_tool_usage(usage_path)
    payload = {
        "success": True,
        "agent_filter": agent,
        "usage_stats_note": "Per-agent tool usage is best-effort: MCP calls only expose an agent when the tool arguments include one. Feedback memories provide stronger attribution.",
        "usage_total_calls": usage.get("total_calls", 0),
        "usage_by_agent": usage.get("agents", {}),
        "recent_calls": usage.get("recent_calls", [])[-20:],
        "feedback_by_agent": feedback_summary,
        "mailbox": _mailbox_report(repo_root),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="mcp_self_check",
            description="检查项目工具台 MCP 自身完整性：工具数、组件覆盖、重复工具、长文件、延迟加载提示。",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_tools": {"type": "boolean", "description": "是否列出所有工具名", "default": True},
                },
            },
        ),
        Tool(
            name="dev_toolkit_architecture_audit",
            description="项目工具台组件化架构审计；等价 mcp_self_check(include_tools=true)，强调维护风险。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="agent_activity_report",
            description="按 agent 汇总项目记忆、MCP 反馈、工具声明使用、邮箱交付元信息和升级建议。",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "可选 agent 过滤，如 codex/opencode/claude", "default": ""},
                    "limit": {"type": "number", "description": "最多读取最近多少条记忆", "default": 200},
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, usage_path: Path, name: str, arguments: dict[str, Any]) -> str:
    if name == "mcp_self_check":
        return mcp_self_check(repo_root, usage_path, include_tools=bool(arguments.get("include_tools", True)))
    if name == "dev_toolkit_architecture_audit":
        return mcp_self_check(repo_root, usage_path, include_tools=True)
    if name == "agent_activity_report":
        return agent_activity_report(
            repo_root,
            usage_path,
            agent=arguments.get("agent", ""),
            limit=int(arguments.get("limit", 200)),
        )
    raise ValueError(f"未知洞察工具: {name}")
