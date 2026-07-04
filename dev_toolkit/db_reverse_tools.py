"""Read-only database reverse audit tools for the project toolkit MCP server."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

try:
    from dev_toolkit.config_loader import load_config
    from dev_toolkit.sql_guard import check_sql_readonly, readonly_psql_env
except ModuleNotFoundError:
    from config_loader import load_config
    from sql_guard import check_sql_readonly, readonly_psql_env

TOOL_NAMES = {"db_reverse_audit"}
DEFAULT_MAX_TABLES = 200
REFERENCE_SCAN_ROOTS = ("backend/app", "modules")
SKIP_PATH_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "sandbox",
    "dist",
    "build",
}
SCAN_SUFFIXES = {".py", ".json", ".ts", ".tsx", ".vue", ".md", ".sql"}
OWNER_ALIASES = {
    "kb": "knowledge",
    "knowledge": "knowledge",
    "framework": "framework",
    "imagegen": "image-gen",
    "image_gen": "image-gen",
    "docs_open": "docs-open",
    "docsopen": "docs-open",
}
EXPECTED_EMPTY_PATTERNS = (
    "approval",
    "approvals",
    "review",
    "reviews",
    "result",
    "results",
    "version",
    "versions",
    "share",
    "shares",
    "read",
    "reads",
    "setting",
    "settings",
    "notification",
    "notifications",
    "experience",
    "experiences",
    "link",
    "links",
    "merge_log",
    "aliases",
    "disambiguation",
)


@dataclass(frozen=True)
class ModuleHint:
    module: str
    has_manifest: bool
    manifest_public_action_count: int
    has_router: bool
    has_capability_registration: bool


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="db_reverse_audit",
            description=(
                "从数据库表反向审计代码/模块链路。只读 DB，输出空表、非空表、"
                "疑似 owner、router/manifest/capability hints 和下一步建议。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "table_filter": {"type": "string", "description": "表名包含过滤，默认全部", "default": ""},
                    "max_tables": {"type": "number", "description": "最多审计表数", "default": DEFAULT_MAX_TABLES},
                    "include_code_references": {
                        "type": "boolean",
                        "description": "是否扫描 backend/app 与 modules 下的代码引用",
                        "default": True,
                    },
                    "count_rows": {
                        "type": "boolean",
                        "description": "是否逐表 SELECT count(*)。关闭后只做结构/代码链路提示。",
                        "default": True,
                    },
                },
            },
        )
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    if name != "db_reverse_audit":
        raise ValueError(f"未知数据库反向审计工具: {name}")
    result = await db_reverse_audit(
        repo_root,
        table_filter=arguments.get("table_filter", ""),
        max_tables=int(arguments.get("max_tables", DEFAULT_MAX_TABLES)),
        include_code_references=bool(arguments.get("include_code_references", True)),
        count_rows=bool(arguments.get("count_rows", True)),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


def _load_db_dsn(repo_root: Path) -> str:
    data = load_config(repo_root)
    return str(data["db_dsn"])


async def _execute_sql(
    query: str,
    *,
    dsn: str | None = None,
    columns: Sequence[str] | None = None,
    timeout: int = 60,
) -> list[dict[str, Any]]:
    check_sql_readonly(query)
    if not dsn:
        raise ValueError("dsn is required")
    cmd = [
        "psql",
        dsn,
        "-X",
        "-q",
        "-t",
        "-A",
        "-F",
        "|",
        "--no-align",
        "--field-separator=|",
        "-c",
        query,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=readonly_psql_env(os.environ),
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace").strip() or "SQL execution failed")
    names = list(columns or [])
    rows: list[dict[str, Any]] = []
    for raw_line in stdout.decode(errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        values = line.split("|")
        if names:
            rows.append({name: values[index] if index < len(values) else "" for index, name in enumerate(names)})
        else:
            rows.append({f"col{index}": value for index, value in enumerate(values)})
    return rows


async def _list_public_tables(dsn: str, table_filter: str, max_tables: int) -> list[str]:
    rows = await _execute_sql(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        dsn=dsn,
        columns=("table_name",),
    )
    needle = table_filter.strip().lower()
    tables = [str(row["table_name"]) for row in rows]
    if needle:
        tables = [table for table in tables if needle in table.lower()]
    return tables[: max(1, max_tables)]


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _count_table_rows(dsn: str, table: str) -> dict[str, Any]:
    query = f"SELECT count(*) FROM {_quote_identifier('public')}.{_quote_identifier(table)}"
    rows = await _execute_sql(query, dsn=dsn, columns=("count",), timeout=30)
    raw_count = rows[0]["count"] if rows else "0"
    return {"row_count": int(raw_count), "count_error": ""}


def _safe_read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _public_action_count(manifest: dict[str, Any]) -> int:
    actions = manifest.get("public_actions", {})
    if isinstance(actions, dict):
        return len(actions)
    if isinstance(actions, list):
        return len(actions)
    return 0


def _file_tree_contains(path: Path, pattern: str) -> bool:
    if not path.exists():
        return False
    for file_path in path.rglob("*.py"):
        if any(part in SKIP_PATH_PARTS for part in file_path.parts):
            continue
        try:
            if pattern in file_path.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def _module_hints(repo_root: Path) -> dict[str, ModuleHint]:
    hints: dict[str, ModuleHint] = {}
    modules_dir = repo_root / "modules"
    if not modules_dir.exists():
        return hints
    for module_dir in sorted(path for path in modules_dir.iterdir() if path.is_dir()):
        manifest_path = module_dir / "manifest.json"
        manifest = _safe_read_json(manifest_path)
        backend_dir = module_dir / "backend"
        hints[module_dir.name] = ModuleHint(
            module=module_dir.name,
            has_manifest=manifest_path.exists(),
            manifest_public_action_count=_public_action_count(manifest),
            has_router=(backend_dir / "router.py").exists(),
            has_capability_registration=_file_tree_contains(backend_dir, "register_capability("),
        )
    return hints


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _owner_for_table(table: str, hints: dict[str, ModuleHint]) -> dict[str, Any]:
    table_lower = table.lower()
    first = table_lower.split("_", 1)[0]
    two_part = "_".join(table_lower.split("_")[:2])
    compact_table = _compact(table_lower)
    alias_owner = OWNER_ALIASES.get(two_part) or OWNER_ALIASES.get(first)
    if alias_owner == "framework":
        return {"type": "framework", "module": "", "confidence": 95, "reason": "framework_* table prefix"}
    if alias_owner and alias_owner in hints:
        return {"type": "module", "module": alias_owner, "confidence": 90, "reason": f"known prefix alias {first}"}

    for module in sorted(hints):
        module_norm = module.replace("-", "_").lower()
        module_first = module_norm.split("_", 1)[0]
        module_compact = _compact(module)
        if table_lower.startswith(module_norm + "_"):
            return {"type": "module", "module": module, "confidence": 90, "reason": f"matches module prefix {module_norm}_"}
        if table_lower.startswith(module_first + "_"):
            return {"type": "module", "module": module, "confidence": 65, "reason": f"matches module first segment {module_first}_"}
        if compact_table.startswith(module_compact):
            return {"type": "module", "module": module, "confidence": 75, "reason": f"matches compact module name {module_compact}"}

    return {"type": "unknown", "module": "", "confidence": 0, "reason": "no matching module or framework prefix"}


def _iter_scan_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in REFERENCE_SCAN_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            try:
                rel_parts = path.relative_to(repo_root).parts
            except ValueError:
                rel_parts = path.parts
            if any(part in SKIP_PATH_PARTS for part in rel_parts):
                continue
            files.append(path)
    return files


def _line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _scan_code_references(repo_root: Path, table_names: Sequence[str]) -> dict[str, dict[str, Any]]:
    if not table_names:
        return {}
    references = {table: {"count": 0, "samples": []} for table in table_names}
    pattern = re.compile("|".join(re.escape(table) for table in sorted(table_names, key=len, reverse=True)))
    for path in _iter_scan_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError:
            continue
        for match in pattern.finditer(text):
            table = match.group(0)
            bucket = references[table]
            bucket["count"] += 1
            if len(bucket["samples"]) < 8:
                rel_path = str(path.relative_to(repo_root))
                bucket["samples"].append(f"{rel_path}:{_line_number(text, match.start())}")
    return references


def _hint_for_owner(owner: dict[str, Any], hints: dict[str, ModuleHint]) -> dict[str, Any]:
    module = owner.get("module") or ""
    if owner.get("type") == "framework":
        return {
            "has_manifest": False,
            "has_router": True,
            "has_capability_registration": True,
            "manifest_public_action_count": 0,
            "note": "framework table; inspect backend/app routes/services instead of module manifest",
        }
    hint = hints.get(module)
    if not hint:
        return {
            "has_manifest": False,
            "has_router": False,
            "has_capability_registration": False,
            "manifest_public_action_count": 0,
            "note": "no module hint found",
        }
    return {
        "has_manifest": hint.has_manifest,
        "has_router": hint.has_router,
        "has_capability_registration": hint.has_capability_registration,
        "manifest_public_action_count": hint.manifest_public_action_count,
        "note": "",
    }


def _issues_for_table(table: dict[str, Any]) -> list[str]:
    row_count = table.get("row_count")
    refs = int(table.get("code_reference_count", 0))
    owner = table["likely_owner"]
    module_hint = table["module_hint"]
    expected_empty = any(pattern in str(table["table"]).lower() for pattern in EXPECTED_EMPTY_PATTERNS)
    issues: list[str] = []
    if row_count == 0 and refs > 0 and not expected_empty:
        issues.append("code_without_data")
    if row_count and refs == 0:
        issues.append("data_without_code_reference")
    if owner["type"] == "unknown" and refs == 0:
        issues.append("orphan_table")
    if row_count and owner["type"] == "module":
        if not module_hint["has_router"]:
            issues.append("data_without_router_hint")
        if not module_hint["has_capability_registration"] and module_hint["manifest_public_action_count"] == 0:
            issues.append("data_without_registered_capability_hint")
    return issues


def _empty_classification(table: dict[str, Any]) -> dict[str, str]:
    row_count = table.get("row_count")
    if row_count is None:
        return {"level": "unknown", "reason": "row counting disabled or failed"}
    if row_count > 0:
        return {"level": "not_empty", "reason": "table has rows"}

    table_name = str(table["table"]).lower()
    refs = int(table.get("code_reference_count", 0))
    owner = table["likely_owner"]
    module_hint = table["module_hint"]
    if any(pattern in table_name for pattern in EXPECTED_EMPTY_PATTERNS):
        return {
            "level": "expected_empty",
            "reason": "optional lifecycle/audit/history table; empty can be normal until that flow is used",
        }
    if refs > 0 or module_hint["has_router"] or module_hint["has_capability_registration"]:
        return {
            "level": "requires_flow_probe",
            "reason": "table has code/module linkage but no rows; verify the owning flow with probe/call_capability",
        }
    if owner["type"] == "unknown":
        return {"level": "suspicious_empty", "reason": "no clear owner and no obvious code path"}
    return {"level": "suspicious_empty", "reason": "owned table is empty but no public flow hint was found"}


def _probe_suggestion(table: dict[str, Any]) -> str:
    owner = table["likely_owner"]
    table_name = table["table"]
    if owner["type"] == "module":
        module = owner["module"]
        module_hint = table["module_hint"]
        if module_hint["has_capability_registration"] or module_hint["manifest_public_action_count"]:
            return f"Run capabilities(module='{module}') then call_capability one read/write happy path that should touch {table_name}."
        if module_hint["has_router"]:
            return f"Inspect modules/{module}/backend/router.py routes, then probe the smallest endpoint expected to touch {table_name}."
        return f"Inspect modules/{module}/README.md and manifest.json to confirm whether {table_name} is still part of the module contract."
    if owner["type"] == "framework":
        return f"Use routes(filter='{table_name.split('_', 2)[0]}') and probe the framework endpoint expected to touch {table_name}."
    return f"Search code_reference_samples and migration/init files for {table_name}; if no owner appears, mark as legacy candidate before any cleanup."


def _summaries(tables: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    def count_value(row: dict[str, Any]) -> int | None:
        value = row.get("row_count")
        return value if isinstance(value, int) else None

    def slim(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "table": row["table"],
            "row_count": row.get("row_count"),
            "likely_owner": row["likely_owner"],
            "code_reference_count": row["code_reference_count"],
            "empty_classification": row["empty_classification"],
            "issues": row["issues"],
        }

    return {
        "empty_tables": [slim(row) for row in tables if count_value(row) == 0],
        "non_empty_tables": [slim(row) for row in tables if (count_value(row) or 0) > 0],
        "expected_empty": [slim(row) for row in tables if row["empty_classification"]["level"] == "expected_empty"],
        "suspicious_empty": [slim(row) for row in tables if row["empty_classification"]["level"] == "suspicious_empty"],
        "requires_flow_probe": [
            slim(row) for row in tables if row["empty_classification"]["level"] == "requires_flow_probe"
        ],
        "orphan_tables": [slim(row) for row in tables if "orphan_table" in row["issues"]],
        "code_without_data": [slim(row) for row in tables if "code_without_data" in row["issues"]],
        "data_without_registered_capability": [
            slim(row) for row in tables if "data_without_registered_capability_hint" in row["issues"]
        ],
        "data_without_code_reference": [
            slim(row) for row in tables if "data_without_code_reference" in row["issues"]
        ],
    }


def _suggest_next_steps(summary: dict[str, list[dict[str, Any]]]) -> list[str]:
    steps = [
        "先看 requires_flow_probe：这些空表有代码或模块链路，应该用 probe/call_capability 跑一次对应 happy path。",
        "expected_empty 不直接判 bug；只有产品流程使用后仍为空，才升级为可疑问题。",
        "再复核 suspicious_empty/orphan_tables：无 owner 或无代码引用的表，确认是否历史遗留或缺少模块命名约定。",
        "对 data_without_registered_capability 表，检查模块是否只写了业务接口但漏了 register_capability 或 manifest public_actions 声明。",
    ]
    if not summary["orphan_tables"]:
        steps.append("当前未发现明显孤儿表，可优先看空表是否属于尚未跑通的业务链路。")
    return steps


async def db_reverse_audit(
    repo_root: Path,
    *,
    table_filter: str = "",
    max_tables: int = DEFAULT_MAX_TABLES,
    include_code_references: bool = True,
    count_rows: bool = True,
) -> dict[str, Any]:
    dsn = _load_db_dsn(repo_root)
    max_tables = max(1, min(max_tables, 500))
    tables = await _list_public_tables(dsn, table_filter, max_tables)
    hints = _module_hints(repo_root)
    references = _scan_code_references(repo_root, tables) if include_code_references else {}

    rows: list[dict[str, Any]] = []
    for table in tables:
        owner = _owner_for_table(table, hints)
        module_hint = _hint_for_owner(owner, hints)
        ref_info = references.get(table, {"count": 0, "samples": []})
        row: dict[str, Any] = {
            "table": table,
            "likely_owner": owner,
            "module_hint": module_hint,
            "code_reference_count": ref_info["count"],
            "code_reference_samples": ref_info["samples"],
            "row_count": None,
            "count_error": "",
        }
        if count_rows:
            try:
                row.update(await _count_table_rows(dsn, table))
            except Exception as exc:
                row["count_error"] = str(exc)
        row["issues"] = _issues_for_table(row)
        row["empty_classification"] = _empty_classification(row)
        row["next_probe"] = _probe_suggestion(row)
        rows.append(row)

    summary = _summaries(rows)
    return {
        "success": True,
        "read_only": True,
        "scope": {
            "schema": "public",
            "table_filter": table_filter,
            "max_tables": max_tables,
            "count_rows": count_rows,
            "include_code_references": include_code_references,
        },
        "table_count": len(rows),
        **summary,
        "tables": rows,
        "suggested_next_steps": _suggest_next_steps(summary),
    }
