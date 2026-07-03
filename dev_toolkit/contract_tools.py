"""Capability contract drift tools for manifest and runtime registry metadata."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOOL_NAMES = {"capability_contract_diff"}


@dataclass(frozen=True)
class RuntimeCapability:
    module: str
    action: str
    min_role: str
    parameter_keys: tuple[str, ...]
    path: Path
    line: int


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="capability_contract_diff",
            description=(
                "比较 modules/*/manifest.json public_actions 与后端 register_capability 元数据，"
                "输出 action/min_role/参数键漂移。运行时注册为准。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "module": {
                        "type": "string",
                        "description": "模块 key，留空则检查全部模块",
                        "default": "",
                    },
                    "include_parameters": {
                        "type": "boolean",
                        "description": "是否比较 public_actions.parameters 与 register_capability parameters 的参数键",
                        "default": True,
                    },
                },
            },
        )
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    if name != "capability_contract_diff":
        raise ValueError(f"未知契约工具: {name}")
    result = capability_contract_diff(
        repo_root,
        module=str(arguments.get("module") or ""),
        include_parameters=bool(arguments.get("include_parameters", True)),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


def capability_contract_diff(
    repo_root: Path,
    *,
    module: str = "",
    include_parameters: bool = True,
) -> dict[str, Any]:
    modules_dir = repo_root / "modules"
    manifest = _manifest_capabilities(modules_dir, module=module)
    runtime, uncheckable = _runtime_capabilities(modules_dir, repo_root, module=module)

    modules = sorted(set(manifest) | set(runtime))
    diffs: list[dict[str, Any]] = []
    ok_modules: list[str] = []
    for module_key in modules:
        manifest_actions = manifest.get(module_key, {})
        runtime_actions = runtime.get(module_key, {})
        module_diffs: list[dict[str, Any]] = []

        for action in sorted(set(manifest_actions) - set(runtime_actions)):
            module_diffs.append({"kind": "manifest_only", "action": action})
        for action in sorted(set(runtime_actions) - set(manifest_actions)):
            cap = runtime_actions[action]
            module_diffs.append({
                "kind": "runtime_only",
                "action": action,
                "runtime_path": _rel(cap.path, repo_root),
                "runtime_line": cap.line,
            })

        for action in sorted(set(manifest_actions) & set(runtime_actions)):
            manifest_meta = manifest_actions[action]
            runtime_meta = runtime_actions[action]
            if manifest_meta["min_role"] != runtime_meta.min_role:
                module_diffs.append({
                    "kind": "min_role_mismatch",
                    "action": action,
                    "manifest": manifest_meta["min_role"],
                    "runtime": runtime_meta.min_role,
                    "runtime_path": _rel(runtime_meta.path, repo_root),
                    "runtime_line": runtime_meta.line,
                })
            if include_parameters:
                manifest_keys = tuple(sorted(manifest_meta["parameter_keys"]))
                runtime_keys = tuple(sorted(runtime_meta.parameter_keys))
                if manifest_keys != runtime_keys:
                    module_diffs.append({
                        "kind": "parameter_keys_mismatch",
                        "action": action,
                        "manifest_only": sorted(set(manifest_keys) - set(runtime_keys)),
                        "runtime_only": sorted(set(runtime_keys) - set(manifest_keys)),
                        "manifest_keys": list(manifest_keys),
                        "runtime_keys": list(runtime_keys),
                        "runtime_path": _rel(runtime_meta.path, repo_root),
                        "runtime_line": runtime_meta.line,
                    })

        if module_diffs:
            diffs.append({"module": module_key, "diffs": module_diffs})
        elif manifest_actions or runtime_actions:
            ok_modules.append(module_key)

    filtered_uncheckable = [
        item for item in uncheckable
        if not module or item["module"] == module or item["module"] == ""
    ]
    return {
        "success": not diffs and not filtered_uncheckable,
        "module_filter": module,
        "include_parameters": include_parameters,
        "summary": {
            "checked_modules": len(modules),
            "ok_modules": len(ok_modules),
            "modules_with_drift": len(diffs),
            "uncheckable_sites": len(filtered_uncheckable),
        },
        "diffs": diffs,
        "uncheckable_sites": filtered_uncheckable,
    }


def _manifest_capabilities(modules_dir: Path, *, module: str = "") -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for manifest_path in sorted(modules_dir.glob("*/manifest.json")):
        module_key = manifest_path.parent.name
        if module and module_key != module:
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        actions: dict[str, dict[str, Any]] = {}
        public_actions = data.get("public_actions") or []
        if isinstance(public_actions, dict):
            iterable = [
                {"action": action, **detail}
                for action, detail in public_actions.items()
                if isinstance(detail, dict)
            ]
        elif isinstance(public_actions, list):
            iterable = public_actions
        else:
            iterable = []
        for item in iterable:
            if isinstance(item, str):
                actions[item] = {"min_role": "viewer", "parameter_keys": tuple()}
                continue
            if not isinstance(item, dict):
                continue
            action = item.get("action") or item.get("name")
            if not isinstance(action, str) or not action:
                continue
            actions[action] = {
                "min_role": str(item.get("min_role") or "viewer"),
                "parameter_keys": _parameter_keys(item.get("parameters")),
            }
        result[module_key] = actions
    return result


def _runtime_capabilities(
    modules_dir: Path,
    repo_root: Path,
    *,
    module: str = "",
) -> tuple[dict[str, dict[str, RuntimeCapability]], list[dict[str, Any]]]:
    result: dict[str, dict[str, RuntimeCapability]] = {}
    uncheckable: list[dict[str, Any]] = []
    for path in sorted(modules_dir.glob("*/backend/**/*.py")):
        if module and path.relative_to(modules_dir).parts[0] != module:
            continue
        capabilities, dynamic_sites = _registered_capabilities(path, repo_root)
        for item in dynamic_sites:
            if not item["module"] or not module or item["module"] == module:
                uncheckable.append(item)
        for cap in capabilities:
            if cap.module.startswith("_"):
                continue
            if module and cap.module != module:
                continue
            result.setdefault(cap.module, {})[cap.action] = cap
    return result, uncheckable


def _registered_capabilities(path: Path, repo_root: Path) -> tuple[list[RuntimeCapability], list[dict[str, Any]]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return [], [{"module": "", "path": _rel(path, repo_root), "line": 0, "reason": "syntax_error"}]

    constants = _module_constants(tree)
    capabilities: list[RuntimeCapability] = []
    dynamic_sites: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            capabilities.extend(_tuple_capabilities(node, path))
            continue
        if not isinstance(node, ast.Call) or _call_name(node) != "register_capability":
            continue

        module = _literal_string(node.args[0], constants) if len(node.args) > 0 else None
        action = _literal_string(node.args[1], constants) if len(node.args) > 1 else None
        if not module or not action:
            dynamic_sites.append({
                "module": module or "",
                "path": _rel(path, repo_root),
                "line": node.lineno,
                "reason": "dynamic_module_or_action",
            })
            continue

        min_role = "viewer"
        parameter_keys: tuple[str, ...] = tuple()
        parameters_checked = False
        for keyword in node.keywords:
            if keyword.arg == "min_role":
                min_role = _literal_string(keyword.value, constants) or min_role
            elif keyword.arg == "parameters":
                parameters_checked = True
                parameter_keys = _parameter_keys(_literal_value(keyword.value, constants))

        if not parameters_checked:
            parameter_keys = tuple()
        capabilities.append(RuntimeCapability(module, action, min_role, parameter_keys, path, node.lineno))
    return capabilities, dynamic_sites


def _tuple_capabilities(node: ast.Assign, path: Path) -> list[RuntimeCapability]:
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return []
    if node.targets[0].id != "capabilities" or not isinstance(node.value, ast.List):
        return []

    result: list[RuntimeCapability] = []
    for item in node.value.elts:
        if not isinstance(item, ast.Tuple) or len(item.elts) < 7:
            continue
        module = _literal_string(item.elts[0], {})
        action = _literal_string(item.elts[1], {})
        min_role = _literal_string(item.elts[6], {}) or "viewer"
        parameters = _literal_value(item.elts[4], {}) if len(item.elts) > 4 else None
        if module and action:
            result.append(RuntimeCapability(
                module,
                action,
                min_role,
                _parameter_keys(parameters),
                path,
                item.lineno,
            ))
    return result


def _module_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        value = _literal_string(node.value, {})
        if value is not None:
            constants[node.targets[0].id] = value
    return constants


def _literal_string(node: ast.AST, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _literal_value(node: ast.AST, constants: dict[str, str]) -> Any:
    if isinstance(node, ast.Name) and node.id in constants:
        return constants[node.id]
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _parameter_keys(parameters: Any) -> tuple[str, ...]:
    if not parameters:
        return tuple()
    if isinstance(parameters, dict):
        properties = parameters.get("properties")
        if isinstance(properties, dict):
            return tuple(sorted(str(key) for key in properties))
        return tuple(sorted(str(key) for key in parameters))
    if isinstance(parameters, list):
        keys: list[str] = []
        for item in parameters:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                keys.append(item["name"])
            elif isinstance(item, str):
                keys.append(item)
        return tuple(sorted(keys))
    return tuple()


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)
