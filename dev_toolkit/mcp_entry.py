"""Shared MCP entrypoint metadata for the project toolkit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SERVER_NAME = "project_toolkit"
SERVER_DISPLAY_NAME = "项目工具台"
SERVER_VERSION = "1.0.0"
DEFAULT_COMMAND = "python3.14"
SERVER_SCRIPT = Path("dev_toolkit") / "server.py"


def expected_server_config(repo_root: Path) -> dict[str, Any]:
    """Return the stdio MCP declaration expected in .mcp.json."""
    return {
        "command": DEFAULT_COMMAND,
        "args": [str(SERVER_SCRIPT)],
        "cwd": str(repo_root),
        "env": {"PYTHONPATH": "."},
    }


def load_declared_server_config(repo_root: Path, server_name: str = SERVER_NAME) -> dict[str, Any]:
    config_path = repo_root / ".mcp.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(".mcp.json missing mcpServers object")
    declared = servers.get(server_name)
    if not isinstance(declared, dict):
        raise ValueError(f".mcp.json missing {server_name!r} server declaration")
    return declared


def validate_declared_server_config(repo_root: Path) -> dict[str, Any]:
    """Compare .mcp.json with the canonical project toolkit entrypoint."""
    expected = expected_server_config(repo_root)
    declared = load_declared_server_config(repo_root)
    mismatches = {
        key: {"expected": value, "actual": declared.get(key)}
        for key, value in expected.items()
        if declared.get(key) != value
    }
    script_path = repo_root / SERVER_SCRIPT
    payload = {
        "success": not mismatches and script_path.is_file(),
        "server_name": SERVER_NAME,
        "server_display_name": SERVER_DISPLAY_NAME,
        "server_version": SERVER_VERSION,
        "config_path": str(repo_root / ".mcp.json"),
        "expected": expected,
        "declared": declared,
        "mismatches": mismatches,
        "script_exists": script_path.is_file(),
        "script_path": str(script_path),
    }
    return payload
