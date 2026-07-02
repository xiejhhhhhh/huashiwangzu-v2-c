"""Boundary regression tests for cross-module decoupling contracts.

Each test asserts a specific boundary rule that must not be violated.
These are read-only static analyses (no DB, no server).
"""

import ast
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _literal(node: ast.AST) -> object:
    return ast.literal_eval(node)


def _parameter_keys(parameters: object) -> set[str]:
    if not isinstance(parameters, dict):
        return set()
    properties = parameters.get("properties")
    if parameters.get("type") == "object" and isinstance(properties, dict):
        return set(properties)
    return set(parameters)


def _module_manifest_actions(module_key: str) -> dict[str, dict]:
    manifest_path = PROJECT_ROOT / "modules" / module_key / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        action["action"]: action
        for action in manifest.get("public_actions", [])
        if isinstance(action, dict) and action.get("action")
    }


def _registered_capabilities(module_key: str) -> list[dict]:
    backend_dir = PROJECT_ROOT / "modules" / module_key / "backend"
    registrations: list[dict] = []
    for path in backend_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "id", None) != "register_capability":
                continue
            if len(node.args) < 2:
                continue
            module_name = _literal(node.args[0])
            action_name = _literal(node.args[1])
            if module_name != module_key or not isinstance(action_name, str):
                continue
            keywords = {
                keyword.arg: _literal(keyword.value)
                for keyword in node.keywords
                if keyword.arg in {"parameters", "min_role"}
            }
            registrations.append({
                "action": action_name,
                "line": node.lineno,
                "min_role": keywords.get("min_role", "viewer"),
                "parameters": keywords.get("parameters", {}),
            })
    return registrations


def _assert_manifest_matches_registered_capabilities(module_key: str) -> None:
    manifest_actions = _module_manifest_actions(module_key)
    registrations = _registered_capabilities(module_key)
    registered_actions: dict[str, dict] = {}
    duplicate_actions: dict[str, list[int]] = {}

    for registration in registrations:
        action = registration["action"]
        if action in registered_actions:
            duplicate_actions.setdefault(action, [registered_actions[action]["line"]]).append(
                registration["line"]
            )
        registered_actions[action] = registration

    assert duplicate_actions == {}, (
        f"{module_key} must register each public capability once, got {duplicate_actions}"
    )
    assert set(manifest_actions) == set(registered_actions), (
        f"{module_key} manifest/register actions drift: "
        f"manifest_only={sorted(set(manifest_actions) - set(registered_actions))}, "
        f"register_only={sorted(set(registered_actions) - set(manifest_actions))}"
    )

    for action, manifest_action in manifest_actions.items():
        registered_action = registered_actions[action]
        assert manifest_action.get("min_role", "viewer") == registered_action["min_role"], (
            f"{module_key}:{action} min_role drift"
        )
        assert _parameter_keys(manifest_action.get("parameters", {})) == _parameter_keys(
            registered_action["parameters"]
        ), f"{module_key}:{action} parameter names drift"


def test_file_transfer_no_knowledge_ingest_hardcode() -> None:
    """file_transfer.py must not hardcode 'knowledge' + 'ingest'."""
    source = _read("backend/app/routers/file_transfer.py")
    # The old hardcoded pattern was: call_capability("knowledge", "ingest", ...)
    # Now it should only emit_module_event, never reference 'knowledge'+'ingest'
    assert '"knowledge"' not in source or '"ingest"' not in source, (
        "file_transfer.py must not hardcode knowledge:ingest"
    )


def test_agent_admin_no_direct_memory_table_read() -> None:
    """agent admin.py must not reference memory module tables directly."""
    source = _read("modules/agent/backend/handlers/admin.py")
    forbidden = ["agent_memory", "memory_links", "agent_experiences"]
    for table in forbidden:
        assert table not in source, (
            f"admin.py must not directly reference '{table}' table"
        )


def test_memory_manifest_has_overview_stats() -> None:
    """memory manifest.json must declare overview_stats public action."""
    manifest = _read("modules/memory/manifest.json")
    assert "overview_stats" in manifest, (
        "memory manifest.json must declare 'overview_stats' public action"
    )


def test_memory_router_registers_overview_stats() -> None:
    """memory router.py must register overview_stats capability."""
    source = _read("modules/memory/backend/router.py")
    assert '"memory", "overview_stats"' in source or "'memory', 'overview_stats'" in source, (
        "memory router.py must register 'overview_stats' capability"
    )


def test_memory_router_overview_stats_min_role_admin() -> None:
    """memory overview_stats must have min_role='admin'."""
    source = _read("modules/memory/backend/router.py")
    assert "min_role=\"admin\"" in source or "min_role='admin'", (
        "memory overview_stats registration must require admin role"
    )


def test_knowledge_manifest_has_file_uploaded_event_handler() -> None:
    """knowledge manifest.json must declare file.uploaded event handler."""
    manifest = _read("modules/knowledge/manifest.json")
    assert "file.uploaded" in manifest, (
        "knowledge manifest.json must declare 'file.uploaded' event handler"
    )


def test_no_cross_module_import_in_non_sandbox_code() -> None:
    """Non-sandbox code must not import from other modules."""
    checks = [
        ("backend/app/routers/file_transfer.py", "from modules."),
        ("backend/app/services/app_service.py", "from modules."),
        ("modules/agent/backend/handlers/admin.py", "from modules."),
    ]
    for filepath, pattern in checks:
        source = _read(filepath)
        assert pattern not in source, (
            f"{filepath} must not use cross-module import pattern '{pattern}'"
        )


def test_desktop_tools_list_apps_uses_current_app_contract() -> None:
    """desktop-tools must read public actions from the current App model field."""
    source = _read("modules/desktop-tools/backend/router.py")
    assert "app.backend_config" not in source
    assert "app.public_actions" in source


def test_memory_manifest_matches_registered_capabilities() -> None:
    """memory public_actions must match its registered capability contract."""
    _assert_manifest_matches_registered_capabilities("memory")


def test_desktop_tools_manifest_matches_registered_capabilities() -> None:
    """desktop-tools public_actions must match its registered capability contract."""
    _assert_manifest_matches_registered_capabilities("desktop-tools")
