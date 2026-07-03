from __future__ import annotations

import json
from pathlib import Path

from dev_toolkit.contract_tools import capability_contract_diff, handles_tool, tool_definitions


def _write_demo_module(root: Path, *, manifest_params: dict, runtime_params: dict) -> None:
    module_dir = root / "modules" / "demo" / "backend"
    module_dir.mkdir(parents=True)
    manifest = {
        "key": "demo",
        "public_actions": [
            {
                "action": "create",
                "description": "Create demo item",
                "parameters": manifest_params,
                "min_role": "editor",
            }
        ],
    }
    (root / "modules" / "demo" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    (module_dir / "router.py").write_text(
        "from app.services.module_registry import register_capability\n\n"
        "async def _handler(params, caller):\n"
        "    return {}\n\n"
        "register_capability(\n"
        "    'demo',\n"
        "    'create',\n"
        "    _handler,\n"
        "    parameters="
        + repr(runtime_params)
        + ",\n"
        "    min_role='editor',\n"
        ")\n",
        encoding="utf-8",
    )


def test_contract_tool_component_exports_contract() -> None:
    names = {tool.name for tool in tool_definitions()}

    assert names == {"capability_contract_diff"}
    assert handles_tool("capability_contract_diff") is True


def test_capability_contract_diff_reports_parameter_drift(tmp_path: Path) -> None:
    _write_demo_module(
        tmp_path,
        manifest_params={"title": "Title"},
        runtime_params={"title": {"type": "string"}, "folder_id": {"type": "integer"}},
    )

    result = capability_contract_diff(tmp_path, module="demo")

    assert result["success"] is False
    assert result["summary"]["modules_with_drift"] == 1
    diff = result["diffs"][0]["diffs"][0]
    assert diff["kind"] == "parameter_keys_mismatch"
    assert diff["runtime_only"] == ["folder_id"]


def test_capability_contract_diff_accepts_matching_metadata(tmp_path: Path) -> None:
    params = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "folder_id": {"type": "integer"},
        },
    }
    _write_demo_module(tmp_path, manifest_params=params, runtime_params=params)

    result = capability_contract_diff(tmp_path, module="demo")

    assert result["success"] is True
    assert result["diffs"] == []


def test_capability_contract_diff_accepts_static_table_registration_loop(tmp_path: Path) -> None:
    module_dir = tmp_path / "modules" / "demo" / "backend"
    module_dir.mkdir(parents=True)
    manifest = {
        "key": "demo",
        "public_actions": [
            {
                "action": "create",
                "description": "Create demo item",
                "parameters": {"title": {"type": "string"}},
                "min_role": "editor",
            }
        ],
    }
    (tmp_path / "modules" / "demo" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    (module_dir / "bootstrap.py").write_text(
        "from app.services.module_registry import register_capability\n\n"
        "async def _handler(params, caller):\n"
        "    return {}\n\n"
        "capabilities = [\n"
        "    ('demo', 'create', _handler, 'desc', 'brief', {'title': {'type': 'string'}}, 'editor'),\n"
        "]\n\n"
        "for module_key, action, handler, desc, brief, params, min_role in capabilities:\n"
        "    register_capability(module_key, action, handler, description=desc, brief=brief, parameters=params, min_role=min_role)\n",
        encoding="utf-8",
    )

    result = capability_contract_diff(tmp_path, module="demo")

    assert result["success"] is True
    assert result["uncheckable_sites"] == []
