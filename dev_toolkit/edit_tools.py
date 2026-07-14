"""Deterministic edit helpers for the project toolkit MCP server."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

try:
    from dev_toolkit.code_tools import lint as run_lint
    from dev_toolkit.code_tools import run_test
    from dev_toolkit.quick_fix import QuickFixError, quick_fix_patch, quick_fix_preview
except ModuleNotFoundError:
    from code_tools import lint as run_lint
    from code_tools import run_test
    from quick_fix import QuickFixError, quick_fix_patch, quick_fix_preview

TOOL_NAMES = {
    "batch_quick_fix_preview",
    "batch_quick_fix_apply",
    "edit_recipe_catalog",
    "edit_recipe_preview",
    "edit_recipe_apply",
}

MAX_OPERATIONS = 50
MAX_WORKERS = 8


def _jsonish(value: Any, default: Any, field_name: str) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must be valid JSON") from exc
    return value


def _as_list(value: Any, field_name: str) -> list[Any]:
    parsed = _jsonish(value, [], field_name)
    if not isinstance(parsed, list):
        raise ValueError(f"{field_name} must be a list")
    return parsed


def _as_dict(value: Any, field_name: str) -> dict[str, Any]:
    parsed = _jsonish(value, {}, field_name)
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be an object")
    return parsed


def _normalize_operations(operations: list[Any]) -> list[dict[str, Any]]:
    if not operations:
        raise ValueError("operations must not be empty")
    if len(operations) > MAX_OPERATIONS:
        raise ValueError(f"operations exceeds safety limit: {MAX_OPERATIONS}")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(operations):
        if not isinstance(raw, dict):
            raise ValueError(f"operation[{index}] must be an object")
        for key in ("path", "old_text", "new_text"):
            if key not in raw:
                raise ValueError(f"operation[{index}] missing required field: {key}")
        normalized.append(
            {
                "index": index,
                "path": str(raw["path"]),
                "old_text": str(raw["old_text"]),
                "new_text": str(raw["new_text"]),
                "start_line": raw.get("start_line"),
                "end_line": raw.get("end_line"),
                "expected_old_text_sha256": str(raw.get("expected_old_text_sha256", "")),
            }
        )
    return normalized


def _line_for_offset(text: str, offset: int) -> int:
    if offset <= 0:
        return 1
    return text.count("\n", 0, offset) + 1


def _unique_index(text: str, needle: str, label: str) -> int:
    if not needle:
        raise ValueError(f"{label} must not be empty")
    first = text.find(needle)
    if first < 0:
        raise ValueError(f"{label} not found")
    if text.find(needle, first + max(1, len(needle))) >= 0:
        raise ValueError(f"{label} is ambiguous")
    return first


def _read_repo_text(repo_root: Path, path: str) -> tuple[Path, str]:
    target = (repo_root / path).resolve() if not Path(path).expanduser().is_absolute() else Path(path).expanduser().resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError("path must stay inside repo root") from exc
    if not target.is_file():
        raise ValueError(f"file does not exist: {path}")
    return target, target.read_text(encoding="utf-8")


def recipe_catalog() -> dict[str, Any]:
    return {
        "success": True,
        "recipes": [
            {
                "name": "exact_replace",
                "description": "One exact old_text -> new_text replacement using the quick_fix safety checks.",
                "parameters": ["path", "old_text", "new_text", "start_line?", "end_line?", "expected_old_text_sha256?"],
            },
            {
                "name": "batch_exact_replace",
                "description": "Many exact replacements; preview validates all operations before any apply writes.",
                "parameters": ["operations[]"],
            },
            {
                "name": "delete_exact",
                "description": "Delete one exact text block by replacing it with an empty string.",
                "parameters": ["path", "old_text", "start_line?", "end_line?"],
            },
            {
                "name": "insert_after",
                "description": "Insert text immediately after a unique anchor_text block.",
                "parameters": ["path", "anchor_text", "insert_text", "start_line?", "end_line?"],
            },
            {
                "name": "replace_between_markers",
                "description": "Replace the text between unique start_marker and end_marker, keeping markers by default.",
                "parameters": ["path", "start_marker", "end_marker", "new_inner", "include_markers?"],
            },
            {
                "name": "add_import",
                "description": "Append an import line (e.g. 'import os' or 'from pathlib import Path') after the last existing import. Skips if the import already exists.",
                "parameters": ["path", "import_line", "start_line?", "end_line?"],
            },
            {
                "name": "wrap_in_try_except",
                "description": "Wrap old_text inside try/except Exception as exc block that logs the exception. Keeps the code structure intact.",
                "parameters": ["path", "old_text", "start_line?", "end_line?", "log_message?"],
            },
            {
                "name": "replace_in_file",
                "description": "Replace ALL occurrences of old_text with new_text across the entire file. Unlike exact_replace, this is not scoped to one match.",
                "parameters": ["path", "old_text", "new_text"],
            },
        ],
        "notes": [
            "These recipes are deterministic; they do not call an LLM.",
            "Apply mode first previews every operation. If any preview fails, nothing is written.",
            "Parallel apply rejects multiple operations targeting the same file unless allow_same_file=true.",
        ],
    }


def build_recipe_operations(repo_root: Path, recipe: str, parameters: Any) -> list[dict[str, Any]]:
    params = _as_dict(parameters, "parameters")
    recipe = recipe.strip()
    if recipe == "exact_replace":
        return [_operation_from_params(params)]
    if recipe == "batch_exact_replace":
        return _normalize_operations(_as_list(params.get("operations"), "parameters.operations"))
    if recipe == "delete_exact":
        operation = _operation_from_params(params)
        operation["new_text"] = ""
        return [operation]
    if recipe == "insert_after":
        anchor = str(params.get("anchor_text", ""))
        insert_text = str(params.get("insert_text", ""))
        if not anchor:
            raise ValueError("anchor_text is required")
        return [
            {
                "path": str(params["path"]),
                "old_text": anchor,
                "new_text": anchor + insert_text,
                "start_line": params.get("start_line"),
                "end_line": params.get("end_line"),
                "expected_old_text_sha256": str(params.get("expected_old_text_sha256", "")),
            }
        ]
    if recipe == "replace_between_markers":
        path = str(params["path"])
        start_marker = str(params.get("start_marker", ""))
        end_marker = str(params.get("end_marker", ""))
        new_inner = str(params.get("new_inner", ""))
        include_markers = bool(params.get("include_markers", False))
        _target, text = _read_repo_text(repo_root, path)
        start = _unique_index(text, start_marker, "start_marker")
        end = _unique_index(text, end_marker, "end_marker")
        if end <= start:
            raise ValueError("end_marker must appear after start_marker")
        if include_markers:
            old_text = text[start : end + len(end_marker)]
            new_text = start_marker + new_inner + end_marker
            start_line = _line_for_offset(text, start)
            end_line = _line_for_offset(text, end + len(end_marker) - 1)
        else:
            old_start = start + len(start_marker)
            old_text = text[old_start:end]
            new_text = new_inner
            start_line = _line_for_offset(text, old_start)
            end_line = _line_for_offset(text, max(old_start, end - 1))
        return [
            {
                "path": path,
                "old_text": old_text,
                "new_text": new_text,
                "start_line": start_line,
                "end_line": end_line,
                "expected_old_text_sha256": "",
            }
        ]
    if recipe == "add_import":
        path = str(params["path"])
        import_line = str(params.get("import_line", ""))
        if not import_line:
            raise ValueError("import_line is required")
        _target, text = _read_repo_text(repo_root, path)
        if import_line.strip() in text:
            return []
        lines = text.splitlines(keepends=True)
        last_import_idx = -1
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                last_import_idx = idx
            elif last_import_idx >= 0 and stripped and not stripped.startswith("#"):
                break
        if last_import_idx < 0:
            old_text = lines[0] if lines else ""
            new_text = old_text + import_line + "\n"
        else:
            old_text = lines[last_import_idx]
            new_text = old_text + import_line + "\n"
        return [{
            "path": path,
            "old_text": old_text,
            "new_text": new_text,
            "start_line": params.get("start_line"),
            "end_line": params.get("end_line"),
            "expected_old_text_sha256": "",
        }]
    if recipe == "wrap_in_try_except":
        path = str(params["path"])
        old_text = str(params.get("old_text", ""))
        log_message = str(params.get("log_message", ""))
        if not old_text:
            raise ValueError("old_text is required")
        indent = ""
        first_line = old_text.split("\n")[0]
        if first_line.strip():
            indent = first_line[:len(first_line) - len(first_line.lstrip())]
        pad = indent + "    "
        if log_message:
            wrapped = (
                f"{indent}try:\n"
                f"{pad}{old_text.strip()}\n"
                f"{indent}except Exception as exc:\n"
                f'{pad}logger.warning("{log_message}: %s", exc)\n'
            )
        else:
            wrapped = (
                f"{indent}try:\n"
                f"{pad}{old_text.strip()}\n"
                f"{indent}except Exception as exc:\n"
                f'{pad}logger.warning("Operation failed: %s", exc)\n'
            )
        return [{
            "path": path,
            "old_text": old_text,
            "new_text": wrapped,
            "start_line": params.get("start_line"),
            "end_line": params.get("end_line"),
            "expected_old_text_sha256": "",
        }]
    if recipe == "replace_in_file":
        path = str(params["path"])
        old_text = str(params.get("old_text", ""))
        new_text = str(params.get("new_text", ""))
        if not old_text:
            raise ValueError("old_text is required")
        _target, file_content = _read_repo_text(repo_root, path)
        count = file_content.count(old_text)
        if count == 0:
            return []
        replaced = file_content.replace(old_text, new_text)
        return [{
            "path": path,
            "old_text": file_content,
            "new_text": replaced,
        }]
    raise ValueError(f"unknown edit recipe: {recipe}")


def _operation_from_params(params: dict[str, Any]) -> dict[str, Any]:
    for key in ("path", "old_text", "new_text"):
        if key not in params:
            raise ValueError(f"parameters.{key} is required")
    return {
        "path": str(params["path"]),
        "old_text": str(params["old_text"]),
        "new_text": str(params["new_text"]),
        "start_line": params.get("start_line"),
        "end_line": params.get("end_line"),
        "expected_old_text_sha256": str(params.get("expected_old_text_sha256", "")),
    }


async def _run_one(repo_root: Path, operation: dict[str, Any], apply: bool) -> dict[str, Any]:
    func = quick_fix_patch if apply else quick_fix_preview
    try:
        result = await asyncio.to_thread(
            func,
            repo_root=repo_root,
            path=operation["path"],
            old_text=operation["old_text"],
            new_text=operation["new_text"],
            start_line=operation.get("start_line"),
            end_line=operation.get("end_line"),
            expected_old_text_sha256=operation.get("expected_old_text_sha256", ""),
        )
        result["index"] = operation["index"]
        return result
    except QuickFixError as exc:
        return {"success": False, "index": operation["index"], "path": operation.get("path"), "error": str(exc)}


async def _run_many(repo_root: Path, operations: list[dict[str, Any]], apply: bool, max_workers: int) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(max(1, min(max_workers, MAX_WORKERS)))

    async def guarded(operation: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await _run_one(repo_root, operation, apply=apply)

    return await asyncio.gather(*(guarded(operation) for operation in operations))


def _duplicate_paths(results: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in results:
        path = item.get("path")
        if not isinstance(path, str):
            continue
        if path in seen:
            duplicates.add(path)
        seen.add(path)
    return sorted(duplicates)


async def _verify_after_apply(
    run_command_json,
    repo_root: Path,
    ruff_cli: str,
    lint_paths: Any,
    test_targets: str,
) -> dict[str, Any]:
    lint_items = _jsonish(lint_paths, [], "lint_paths")
    if isinstance(lint_items, str):
        lint_items = [item.strip() for item in lint_items.replace("\n", ",").split(",") if item.strip()]
    if not isinstance(lint_items, list):
        raise ValueError("lint_paths must be a list or comma/newline separated string")
    lint_results = []
    for path in lint_items:
        lint_results.append(json.loads(await run_lint(run_command_json, repo_root, ruff_cli, path=str(path))))
    test_result = None
    if test_targets and test_targets.strip():
        test_result = json.loads(await run_test(run_command_json, repo_root, target=test_targets.strip()))
    return {"lint": lint_results, "test": test_result}


async def batch_quick_fix(
    run_command_json,
    repo_root: Path,
    ruff_cli: str,
    operations: Any,
    apply: bool,
    max_workers: int = 4,
    allow_same_file: bool = False,
    lint_paths: Any = None,
    test_targets: str = "",
) -> str:
    started = time.time()
    normalized = _normalize_operations(_as_list(operations, "operations"))
    for index, operation in enumerate(normalized):
        operation["index"] = index
    preview_results = await _run_many(repo_root, normalized, apply=False, max_workers=max_workers)
    preview_ok = all(item.get("success") for item in preview_results)
    duplicates = _duplicate_paths(preview_results)
    if not apply:
        payload = {
            "success": preview_ok,
            "applied": False,
            "operation_count": len(normalized),
            "max_workers": max_workers,
            "results": preview_results,
            "duplicate_paths": duplicates,
            "duration_seconds": round(time.time() - started, 3),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if not preview_ok:
        payload = {
            "success": False,
            "applied": False,
            "error": "preview failed; no files were written",
            "results": preview_results,
            "duration_seconds": round(time.time() - started, 3),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if duplicates and not allow_same_file:
        payload = {
            "success": False,
            "applied": False,
            "error": "multiple operations target the same file; split them or set allow_same_file=true for sequential apply",
            "duplicate_paths": duplicates,
            "results": preview_results,
            "duration_seconds": round(time.time() - started, 3),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if duplicates:
        apply_results = []
        for operation in normalized:
            apply_results.append(await _run_one(repo_root, operation, apply=True))
    else:
        apply_results = await _run_many(repo_root, normalized, apply=True, max_workers=max_workers)
    apply_ok = all(item.get("success") for item in apply_results)
    verification = None
    if apply_ok and (lint_paths or test_targets):
        verification = await _verify_after_apply(run_command_json, repo_root, ruff_cli, lint_paths, test_targets)
    payload = {
        "success": apply_ok,
        "applied": apply_ok,
        "operation_count": len(normalized),
        "max_workers": 1 if duplicates else max_workers,
        "results": apply_results,
        "verification": verification,
        "duration_seconds": round(time.time() - started, 3),
        "note": "This is a deterministic edit worker. It does not call an LLM or create a sub-agent.",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def edit_recipe(
    run_command_json,
    repo_root: Path,
    ruff_cli: str,
    recipe: str,
    parameters: Any,
    apply: bool,
    max_workers: int = 4,
    allow_same_file: bool = False,
    lint_paths: Any = None,
    test_targets: str = "",
) -> str:
    operations = build_recipe_operations(repo_root, recipe, parameters)
    return await batch_quick_fix(
        run_command_json,
        repo_root,
        ruff_cli,
        operations=operations,
        apply=apply,
        max_workers=max_workers,
        allow_same_file=allow_same_file,
        lint_paths=lint_paths,
        test_targets=test_targets,
    )


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    operation_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "仓库内文件路径"},
            "old_text": {"type": "string", "description": "必须唯一命中的原文块"},
            "new_text": {"type": "string", "description": "替换后的文本块"},
            "start_line": {"type": "number", "description": "可选定位起始行"},
            "end_line": {"type": "number", "description": "可选定位结束行"},
            "expected_old_text_sha256": {"type": "string", "description": "可选 old_text sha256 防漂移", "default": ""},
        },
        "required": ["path", "old_text", "new_text"],
    }
    batch_schema = {
        "type": "object",
        "properties": {
            "operations": {"type": "array", "items": operation_schema, "description": "精准替换操作列表；也可传 JSON 字符串"},
            "max_workers": {"type": "number", "description": "并发 worker 数，上限 8", "default": 4},
            "allow_same_file": {"type": "boolean", "description": "允许同文件顺序写入；默认拒绝避免冲突", "default": False},
            "lint_paths": {"type": "array", "items": {"type": "string"}, "description": "apply 成功后可选 ruff 检查文件列表"},
            "test_targets": {"type": "string", "description": "apply 成功后可选 pytest 目标", "default": ""},
        },
        "required": ["operations"],
    }
    recipe_schema = {
        "type": "object",
        "properties": {
            "recipe": {"type": "string", "description": "recipe 名称；先用 edit_recipe_catalog 查看"},
            "parameters": {"type": "object", "description": "recipe 参数；也可传 JSON 字符串"},
            "max_workers": {"type": "number", "description": "并发 worker 数，上限 8", "default": 4},
            "allow_same_file": {"type": "boolean", "description": "允许同文件顺序写入；默认拒绝避免冲突", "default": False},
            "lint_paths": {"type": "array", "items": {"type": "string"}, "description": "apply 成功后可选 ruff 检查文件列表"},
            "test_targets": {"type": "string", "description": "apply 成功后可选 pytest 目标", "default": ""},
        },
        "required": ["recipe", "parameters"],
    }
    return [
        Tool(
            name="batch_quick_fix_preview",
            description="并发预览多个精准 old_text 替换；只读不写盘，不调用 LLM。",
            inputSchema=batch_schema,
        ),
        Tool(
            name="batch_quick_fix_apply",
            description="并发应用多个精准替换：先全量 preview，通过后原子写盘，可选 lint/test 验证；不调用 LLM。",
            inputSchema=batch_schema,
        ),
        Tool(
            name="edit_recipe_catalog",
            description="列出确定性精准编辑 recipes。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="edit_recipe_preview",
            description="按 recipe 生成精准替换操作并预览 diff；只读不写盘。",
            inputSchema=recipe_schema,
        ),
        Tool(
            name="edit_recipe_apply",
            description="按 recipe 生成精准替换操作并应用；先预览全通过，再写盘，可选 lint/test。",
            inputSchema=recipe_schema,
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(
    run_command_json,
    repo_root: Path,
    ruff_cli: str,
    name: str,
    arguments: dict[str, Any],
) -> str:
    if name == "edit_recipe_catalog":
        return json.dumps(recipe_catalog(), ensure_ascii=False, indent=2)
    if name == "batch_quick_fix_preview":
        return await batch_quick_fix(
            run_command_json,
            repo_root,
            ruff_cli,
            operations=arguments.get("operations"),
            apply=False,
            max_workers=int(arguments.get("max_workers", 4)),
            allow_same_file=bool(arguments.get("allow_same_file", False)),
        )
    if name == "batch_quick_fix_apply":
        return await batch_quick_fix(
            run_command_json,
            repo_root,
            ruff_cli,
            operations=arguments.get("operations"),
            apply=True,
            max_workers=int(arguments.get("max_workers", 4)),
            allow_same_file=bool(arguments.get("allow_same_file", False)),
            lint_paths=arguments.get("lint_paths"),
            test_targets=arguments.get("test_targets", ""),
        )
    if name == "edit_recipe_preview":
        return await edit_recipe(
            run_command_json,
            repo_root,
            ruff_cli,
            recipe=arguments["recipe"],
            parameters=arguments.get("parameters", {}),
            apply=False,
            max_workers=int(arguments.get("max_workers", 4)),
            allow_same_file=bool(arguments.get("allow_same_file", False)),
        )
    if name == "edit_recipe_apply":
        return await edit_recipe(
            run_command_json,
            repo_root,
            ruff_cli,
            recipe=arguments["recipe"],
            parameters=arguments.get("parameters", {}),
            apply=True,
            max_workers=int(arguments.get("max_workers", 4)),
            allow_same_file=bool(arguments.get("allow_same_file", False)),
            lint_paths=arguments.get("lint_paths"),
            test_targets=arguments.get("test_targets", ""),
        )
    raise ValueError(f"未知编辑工具: {name}")
