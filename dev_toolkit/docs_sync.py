"""Documentation currentness tools driven by code facts.

The docs guard keeps long-lived Markdown aligned with manifests, registered
capabilities, sandbox metadata, and repository policy. It intentionally ignores
historical task logs: current docs must describe how the project works now.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dev_toolkit.contract_tools import capability_contract_diff
    from dev_toolkit.module_sandbox_matrix import scan_sandbox_matrix
except ModuleNotFoundError:
    from contract_tools import capability_contract_diff
    from module_sandbox_matrix import scan_sandbox_matrix

TOOL_NAMES = {"docs_snapshot", "docs_audit", "docs_sync"}

DELETED_DOC_REFS = (
    "开发文档/项目记忆",
    "开发文档/变更历史.md",
    "开发文档/变更历史归档.md",
    "开发文档/流程能力审计报告-20260704.md",
    "knowledge_video_analysis_system_plan.md",
    "开发记录.md",
)

HISTORICAL_PATTERNS = (
    "本轮",
    "本次",
    "反向审计",
    "Latest audit",
    "工具台反馈",
    "执行信",
    "验收回信",
)

KEEP_DOCS = (
    "AGENTS.md",
    "README.md",
    "backend/README.md",
    "frontend/README.md",
    "frontend/src/desktop/design-system/README.md",
    "dev_toolkit/README.md",
    "开发文档/README.md",
    "开发文档/01_框架开发文档/README.md",
    "开发文档/02_底层开发文档/README.md",
    "开发文档/03_模块开发文档/README.md",
    "开发文档/算法调优手册.md",
    "开发文档/agent_handoff/START_HERE.md",
    "开发文档/agent_handoff/CURRENT_STATE.md",
    "开发文档/agent_handoff/CONTRACTS.md",
    "开发文档/agent_handoff/ACCEPTANCE.md",
    "开发文档/agent_handoff/TOOLKIT_WORKFLOW.md",
    "开发文档/agent_handoff/CHANGE_POLICY.md",
    "开发文档/agent_handoff/TROUBLESHOOTING.md",
    "开发文档/agent_handoff/MODULE_MAP.md",
)

ALLOWED_MODULE_TYPES = {"app", "orchestrator", "provider", "parser", "viewer", "editor", "service", "demo"}
ALLOWED_MODULE_FAMILIES = {"desktop", "office", "knowledge", "agent", "media", "web", "business", "devtool", "demo"}
ALLOWED_PRODUCT_STATUSES = {"core", "active", "background", "hidden", "demo", "debt", "deprecated"}
BACKGROUND_ENTRY_TYPES = {"parser", "provider", "service", "demo"}
BACKGROUND_STATUSES = {"background", "hidden", "demo", "deprecated"}
FAMILY_ORDER = ("agent", "knowledge", "desktop", "office", "media", "web", "business", "devtool", "demo")
FAMILY_LABELS = {
    "agent": "Agent / Workflow",
    "knowledge": "Knowledge / Content Intelligence",
    "desktop": "Desktop / Viewer / Editor",
    "office": "Office / Parser / Document",
    "media": "AI Media Providers",
    "web": "Web / Browser / External Info",
    "business": "Business Apps",
    "devtool": "Agent Dev Tools",
    "demo": "Demo",
}


@dataclass(frozen=True)
class ModuleDocFacts:
    key: str
    manifest: dict[str, Any]
    actions: list[dict[str, Any]]
    backend_prefix: str
    sandbox: dict[str, Any]


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="docs_snapshot",
            description="只读生成当前代码事实文档快照：manifest/capability/sandbox/README 状态。",
            inputSchema={
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "可选模块 key，留空则全部", "default": ""},
                    "max_modules": {"type": "number", "description": "可选，最多返回多少模块", "default": 200},
                },
            },
        ),
        Tool(
            name="docs_audit",
            description="只读检查文档是否与代码事实漂移，包含断链、能力数、历史垃圾关键词。",
            inputSchema={
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "可选模块 key，留空则全部", "default": ""},
                },
            },
        ),
        Tool(
            name="docs_sync",
            description="按代码事实刷新 CURRENT_STATE、MODULE_MAP 和模块 README 的 DOCS-SYNC 区块。",
            inputSchema={
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "可选模块 key，留空则全部", "default": ""},
                    "scope": {
                        "type": "string",
                        "description": "sync 范围: all/module_map/current_state/module_readmes",
                        "default": "all",
                    },
                    "dry_run": {"type": "boolean", "description": "只预览不写盘", "default": False},
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    module = str(arguments.get("module") or "").strip()
    if name == "docs_snapshot":
        result = docs_snapshot(repo_root, module=module, max_modules=int(arguments.get("max_modules") or 200))
    elif name == "docs_audit":
        result = docs_audit(repo_root, module=module)
    elif name == "docs_sync":
        result = docs_sync(
            repo_root,
            module=module,
            scope=str(arguments.get("scope") or "all"),
            dry_run=bool(arguments.get("dry_run", False)),
        )
    else:
        raise ValueError(f"未知文档工具: {name}")
    return json.dumps(result, ensure_ascii=False, indent=2)


def docs_snapshot(repo_root: Path, *, module: str = "", max_modules: int = 200) -> dict[str, Any]:
    facts = collect_module_facts(repo_root, module=module)
    drift = capability_contract_diff(repo_root, module=module, include_parameters=True)
    modules = {
        item.key: {
            "manifest": manifest_summary(item.manifest),
            "public_actions": item.actions,
            "public_action_count": len(item.actions),
            "backend_prefix": item.backend_prefix,
            "sandbox": item.sandbox,
            "readme_path": f"modules/{item.key}/README.md",
        }
        for item in facts[:max_modules]
    }
    return {
        "success": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "module_filter": module,
        "module_count": len(facts),
        "modules": modules,
        "capability_drift": drift.get("summary", {}),
    }


def docs_audit(repo_root: Path, *, module: str = "") -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    facts = collect_module_facts(repo_root, module=module)
    drift = capability_contract_diff(repo_root, module=module, include_parameters=True)
    if not drift.get("success"):
        issues.append({"level": "BLOCKER", "kind": "capability_drift", "detail": drift.get("summary", {})})

    for item in facts:
        readme = repo_root / "modules" / item.key / "README.md"
        if not readme.exists():
            issues.append({"level": "BLOCKER", "kind": "missing_module_readme", "path": rel(readme, repo_root)})
            continue
        text = read_text(readme)
        expected = len(item.actions)
        count_match = re.search(r"Total public actions:\s*(\d+)", text)
        if count_match and int(count_match.group(1)) != expected:
            issues.append({
                "level": "BLOCKER",
                "kind": "public_action_count_mismatch",
                "path": rel(readme, repo_root),
                "expected": expected,
                "documented": int(count_match.group(1)),
            })
        issues.extend(taxonomy_issues(item))
        if item.actions and "Runtime authority" not in text:
            issues.append({"level": "DEBT", "kind": "missing_capability_source", "path": rel(readme, repo_root)})
        if "Acceptance" not in text and "验收" not in text:
            issues.append({"level": "DEBT", "kind": "missing_acceptance_section", "path": rel(readme, repo_root)})
        if item.key == "excel-engine" and "只暴露 parse" in text:
            issues.append({"level": "BLOCKER", "kind": "stale_excel_parse_only_claim", "path": rel(readme, repo_root)})
        if item.key == "memory" and "All `agent_*` prefix" in text:
            issues.append({"level": "BLOCKER", "kind": "stale_memory_table_prefix", "path": rel(readme, repo_root)})

    for rel_path in existing_keep_docs(repo_root):
        path = repo_root / rel_path
        text = read_text(path)
        for ref in DELETED_DOC_REFS:
            if ref in text:
                issues.append({"level": "BLOCKER", "kind": "deleted_doc_reference", "path": rel_path, "reference": ref})
        for pattern in HISTORICAL_PATTERNS:
            if pattern in text:
                issues.append({"level": "DEBT", "kind": "historical_keyword", "path": rel_path, "keyword": pattern})
        if raw_user_profile_record(text):
            issues.append({"level": "BLOCKER", "kind": "raw_user_profile_record", "path": rel_path})
        if rel_path != "开发文档/agent_handoff/CURRENT_STATE.md" and re.search(r"2026-\d{2}-\d{2}", text):
            issues.append({"level": "DEBT", "kind": "date_in_long_lived_doc", "path": rel_path})

    blocker_count = sum(1 for item in issues if item["level"] == "BLOCKER")
    debt_count = sum(1 for item in issues if item["level"] == "DEBT")
    level = "BLOCKER" if blocker_count else "DEBT" if debt_count else "PASS"
    return {
        "success": blocker_count == 0,
        "level": level,
        "summary": {"blockers": blocker_count, "debts": debt_count, "issues": len(issues)},
        "issues": issues[:300],
    }


def docs_sync(repo_root: Path, *, module: str = "", scope: str = "all", dry_run: bool = False) -> dict[str, Any]:
    scope = scope or "all"
    changed: list[str] = []
    previews: dict[str, str] = {}
    facts = collect_module_facts(repo_root, module=module)

    def write_rel(rel_path: str, content: str) -> None:
        path = repo_root / rel_path
        previews[rel_path] = content
        if dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
        changed.append(rel_path)

    if scope in {"all", "current_state"}:
        write_rel("开发文档/agent_handoff/CURRENT_STATE.md", render_current_state(repo_root, facts))
    if scope in {"all", "module_map"}:
        write_rel("开发文档/agent_handoff/MODULE_MAP.md", render_module_map(facts))
    if scope in {"all", "module_readmes"}:
        for item in facts:
            rel_path = f"modules/{item.key}/README.md"
            existing = read_text(repo_root / rel_path)
            synced = replace_sync_block(existing, "manifest", render_manifest_block(item))
            synced = replace_sync_block(synced, "public_actions", render_public_actions_block(item))
            synced = replace_sync_block(synced, "sandbox", render_sandbox_block(item))
            if synced != existing:
                write_rel(rel_path, synced)
    return {
        "success": True,
        "dry_run": dry_run,
        "scope": scope,
        "module_filter": module,
        "changed": changed,
        "preview_paths": list(previews),
    }


def collect_module_facts(repo_root: Path, *, module: str = "") -> list[ModuleDocFacts]:
    modules_dir = repo_root / "modules"
    sandbox_by_key = {entry["module"]: entry for entry in scan_sandbox_matrix()}
    result: list[ModuleDocFacts] = []
    for manifest_path in sorted(modules_dir.glob("*/manifest.json")):
        key = manifest_path.parent.name
        if key.startswith("_"):
            continue
        if module and key != module:
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        result.append(ModuleDocFacts(
            key=key,
            manifest=manifest,
            actions=normalize_actions(manifest.get("public_actions") or []),
            backend_prefix=detect_backend_prefix(manifest_path.parent),
            sandbox=sandbox_by_key.get(key, {}),
        ))
    return result


def normalize_actions(public_actions: Any) -> list[dict[str, Any]]:
    if isinstance(public_actions, dict):
        iterable = [{"action": action, **detail} for action, detail in public_actions.items() if isinstance(detail, dict)]
    elif isinstance(public_actions, list):
        iterable = public_actions
    else:
        iterable = []
    actions: list[dict[str, Any]] = []
    for item in iterable:
        if isinstance(item, str):
            actions.append({"action": item, "min_role": "viewer", "parameters": {}, "description": ""})
        elif isinstance(item, dict):
            action = item.get("action") or item.get("name")
            if action:
                actions.append({
                    "action": str(action),
                    "min_role": str(item.get("min_role") or "viewer"),
                    "parameters": item.get("parameters") or {},
                    "description": str(item.get("description") or item.get("brief") or ""),
                })
    return sorted(actions, key=lambda item: item["action"])


def detect_backend_prefix(module_dir: Path) -> str:
    router_path = module_dir / "backend" / "router.py"
    if not router_path.exists():
        return "N/A"
    text = read_text(router_path)
    match = re.search(r"APIRouter\(\s*prefix\s*=\s*[\"']([^\"']+)[\"']", text)
    return match.group(1) if match else "declared in router.py"


def manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "key",
        "name",
        "category",
        "module_type",
        "module_family",
        "product_status",
        "window_type",
        "singleton",
        "allow_multiple",
        "show_in_launcher",
        "show_on_desktop",
        "route_prefix",
        "contract_version",
        "module_version",
    )
    return {key: manifest.get(key) for key in keys if key in manifest}


def taxonomy_issues(item: ModuleDocFacts) -> list[dict[str, Any]]:
    manifest = item.manifest
    issues: list[dict[str, Any]] = []
    module_type = str(manifest.get("module_type") or "")
    module_family = str(manifest.get("module_family") or "")
    product_status = str(manifest.get("product_status") or "")
    path = f"modules/{item.key}/manifest.json"
    if module_type not in ALLOWED_MODULE_TYPES:
        issues.append({"level": "BLOCKER", "kind": "invalid_module_type", "path": path, "value": module_type})
    if module_family not in ALLOWED_MODULE_FAMILIES:
        issues.append({"level": "BLOCKER", "kind": "invalid_module_family", "path": path, "value": module_family})
    if product_status not in ALLOWED_PRODUCT_STATUSES:
        issues.append({"level": "BLOCKER", "kind": "invalid_product_status", "path": path, "value": product_status})
    if module_type in BACKGROUND_ENTRY_TYPES and manifest.get("show_in_launcher"):
        issues.append({"level": "DEBT", "kind": "background_module_in_launcher", "path": path, "module_type": module_type})
    if product_status in BACKGROUND_STATUSES and manifest.get("show_on_desktop"):
        issues.append({"level": "DEBT", "kind": "background_module_on_desktop", "path": path, "product_status": product_status})
    if module_type == "demo" and module_family != "demo":
        issues.append({"level": "DEBT", "kind": "demo_family_mismatch", "path": path, "module_family": module_family})
    return issues


def render_current_state(repo_root: Path, facts: list[ModuleDocFacts]) -> str:
    drift = capability_contract_diff(repo_root, include_parameters=True)
    generated = datetime.now(timezone.utc).isoformat()
    return f"""# Current State

Last generated: {generated}

This file is generated from current repository facts. Refresh it with `docs_sync(scope=\"current_state\")`.

## Services

| Item | Current contract |
|---|---|
| Backend | FastAPI on `127.0.0.1:33000`, actual port recorded in `backend/logs/.backend.port` |
| Frontend | Vite dev server on `127.0.0.1:5173` |
| Database | PostgreSQL 17 + pgvector, DB name `华世王镞_v2` |
| Embeddings | bge-m3 OpenAI-compatible endpoint on `127.0.0.1:30000` |

## Code-derived status

| Check | Value |
|---|---|
| Modules with manifests | {len(facts)} |
| Public capabilities in manifests | {sum(len(item.actions) for item in facts)} |
| Capability drift | {drift.get('summary', {})} |

## Current known release risk

Run `release_gate(skip_ui=true, mode=\"preflight\")` for live status. As of the last manual audit, test data pollution may still block a clean release; treat the live gate result as the authority.
"""


def render_module_map(facts: list[ModuleDocFacts]) -> str:
    lines = [
        "# Module Map\n\n",
        "Generated from `modules/*/manifest.json`. Refresh with `docs_sync(scope=\"module_map\")`.\n\n",
        "Modules are physically flat under `modules/{key}`. `module_family` is a logical grouping only; "
        "same-family modules still call each other through the capability bus and must not import or read each other's tables directly.\n\n",
        "## Summary\n\n",
        f"- Total modules: {len(facts)}\n",
        f"- Public capabilities: {sum(len(item.actions) for item in facts)}\n",
        "- Entry cleanup rule: parser/provider/service/demo modules stay out of the launcher unless explicitly justified.\n\n",
    ]
    for family in FAMILY_ORDER:
        group = [item for item in facts if item.manifest.get("module_family") == family]
        if not group:
            continue
        lines.append(f"## {FAMILY_LABELS.get(family, family)}\n\n")
        lines.append("| Module | Name | Type | Status | Entry | Backend | Public actions | README |\n")
        lines.append("|---|---|---|---|---|---|---:|---|\n")
        for item in sorted(group, key=lambda value: (str(value.manifest.get("module_type") or ""), value.key)):
            manifest = item.manifest
            backend = "yes" if manifest.get("backend", {}).get("enabled") else "no"
            entry = entry_summary(manifest)
            lines.append(
                f"| `{item.key}` | {manifest.get('name', item.key)} | `{manifest.get('module_type', '')}` | "
                f"`{manifest.get('product_status', '')}` | {entry} | {backend} | {len(item.actions)} | "
                f"`modules/{item.key}/README.md` |\n"
            )
        lines.append("\n")
    uncategorized = [item for item in facts if item.manifest.get("module_family") not in FAMILY_ORDER]
    if uncategorized:
        lines.append("## Uncategorized\n\n")
        lines.append("| Module | Name | Type | Family | Status | README |\n")
        lines.append("|---|---|---|---|---|---|\n")
        for item in uncategorized:
            manifest = item.manifest
            lines.append(
                f"| `{item.key}` | {manifest.get('name', item.key)} | `{manifest.get('module_type', '')}` | "
                f"`{manifest.get('module_family', '')}` | `{manifest.get('product_status', '')}` | `modules/{item.key}/README.md` |\n"
            )
    return "".join(lines)


def entry_summary(manifest: dict[str, Any]) -> str:
    entries = []
    if manifest.get("show_in_launcher"):
        entries.append("launcher")
    if manifest.get("show_on_desktop"):
        entries.append("desktop")
    return ", ".join(entries) if entries else "background/file/capability"


def render_manifest_block(item: ModuleDocFacts) -> str:
    manifest = item.manifest
    rows = []
    for key, value in manifest_summary(manifest).items():
        rows.append(f"| {key} | `{json.dumps(value, ensure_ascii=False)}` |")
    backend = manifest.get("backend") or {}
    rows.append(f"| backend.enabled | `{json.dumps(backend.get('enabled'), ensure_ascii=False)}` |")
    rows.append(f"| backend.router | `{json.dumps(backend.get('router'), ensure_ascii=False)}` |")
    rows.append(f"| actual backend prefix | `{item.backend_prefix}` |")
    return "\n".join(["| Field | Value |", "|---|---|", *rows])


def render_public_actions_block(item: ModuleDocFacts) -> str:
    lines = [
        "Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.",
        "",
        f"Total public actions: {len(item.actions)}",
        "",
        "| Action | min_role | Parameters | Purpose |",
        "|---|---|---|---|",
    ]
    if not item.actions:
        lines.append("| N/A | N/A | N/A | No public backend capability |")
    for action in item.actions:
        params = summarize_parameters(action.get("parameters"))
        desc = (action.get("description") or "").replace("|", "/")
        lines.append(f"| `{action['action']}` | `{action['min_role']}` | {params} | {desc} |")
    return "\n".join(lines)


def render_sandbox_block(item: ModuleDocFacts) -> str:
    sandbox = item.sandbox
    backend_cmd = sandbox.get("backend_test_cmd") or "N/A"
    frontend_cmd = sandbox.get("frontend_build_cmd") or "N/A"
    return "\n".join([
        "| Area | Status | Verification |",
        "|---|---|---|",
        f"| README | {'PASS' if sandbox.get('readme_exists') else 'DEBT'} | `modules/{item.key}/README.md` |",
        f"| Acceptance matrix | {'PASS' if sandbox.get('readme_acceptance_matrix') else 'DEBT'} | {sandbox.get('readme_acceptance_reason') or 'present'} |",
        f"| Backend sandbox | {'PASS' if sandbox.get('has_test_module') else 'SKIP'} | `{backend_cmd}` |",
        f"| Frontend sandbox | {'PASS' if sandbox.get('frontend_build_cmd') else 'SKIP'} | `{frontend_cmd}` |",
        f"| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module {item.key} --check` |",
    ])


def summarize_parameters(parameters: Any) -> str:
    if not parameters:
        return "none"
    if isinstance(parameters, dict):
        props = parameters.get("properties") if isinstance(parameters.get("properties"), dict) else parameters
        return ", ".join(f"`{key}`" for key in sorted(str(k) for k in props.keys())) or "object"
    if isinstance(parameters, list):
        keys = []
        for item in parameters:
            if isinstance(item, dict):
                name = item.get("name") or item.get("key")
                if name:
                    keys.append(str(name))
        return ", ".join(f"`{key}`" for key in sorted(keys)) or "list"
    return "object"


def replace_sync_block(text: str, section: str, content: str) -> str:
    pattern = re.compile(
        rf"<!-- DOCS-SYNC: section={re.escape(section)} -->.*?<!-- /DOCS-SYNC -->",
        flags=re.DOTALL,
    )
    replacement = f"<!-- DOCS-SYNC: section={section} -->\n{content}\n<!-- /DOCS-SYNC -->"
    if pattern.search(text):
        return pattern.sub(replacement, text)
    return text


def existing_keep_docs(repo_root: Path) -> list[str]:
    rels = [rel_path for rel_path in KEEP_DOCS if (repo_root / rel_path).exists()]
    rels.extend(
        str(path.relative_to(repo_root))
        for path in sorted((repo_root / "modules").glob("*/README.md"))
        if not path.parent.name.startswith("_")
    )
    return rels


def raw_user_profile_record(text: str) -> bool:
    """Detect raw profile JSON/records in long-lived docs without blocking policy prose."""
    if "schema_version" not in text or '"profiles"' not in text:
        return False
    return any(marker in text for marker in ('"candidates"', '"preferences"', '"habits"', '"taboos"'))


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)
