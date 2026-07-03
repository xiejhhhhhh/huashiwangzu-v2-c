from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest

from dev_toolkit.mcp_entry import expected_server_config, validate_declared_server_config

REPO_ROOT = Path(__file__).resolve().parent.parent
pytest.importorskip("mcp")
from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

REQUIRED_TOOLS = {
    "agent_board_claim",
    "db_reverse_audit",
    "module_sandbox_matrix",
    "opencode_dispatch_letter",
    "opencode_pty_start",
    "opencode_sdk_job_continue",
    "opencode_sdk_job_dispatch_letter",
    "opencode_sdk_job_list",
    "opencode_sdk_job_notifications",
    "opencode_sdk_job_status",
    "opencode_sdk_job_submit",
    "opencode_sdk_messages",
    "opencode_sdk_prompt",
    "release_gate",
    "tool_job_notifications",
    "tool_job_status",
    "tool_job_submit",
}


def test_mcp_json_declares_stable_stdio_entrypoint() -> None:
    result = validate_declared_server_config(REPO_ROOT)

    assert result["success"] is True
    assert result["declared"] == expected_server_config(REPO_ROOT)
    assert result["script_exists"] is True


def test_stdio_entrypoints_list_required_tools() -> None:
    async def list_tools(command: str, args: list[str], cwd: str):
        params = StdioServerParameters(command=command, args=args, cwd=cwd)
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init = await session.initialize()
                tools = await session.list_tools()
        assert init.serverInfo.name == "项目工具台"
        assert init.serverInfo.version == "1.0.0"
        return tools.tools

    declared = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["项目工具台"]

    async def run() -> None:
        declared_tools = await list_tools(declared["command"], declared["args"], declared["cwd"])
        direct_tools = await list_tools("python3.14", ["dev_toolkit/server.py"], str(REPO_ROOT))
        declared_names = {tool.name for tool in declared_tools}
        direct_names = {tool.name for tool in direct_tools}
        assert REQUIRED_TOOLS.issubset(declared_names)
        assert REQUIRED_TOOLS.issubset(direct_names)

        release_tool = next(tool for tool in direct_tools if tool.name == "release_gate")
        properties = release_tool.inputSchema["properties"]
        assert properties["mode"]["default"] == "preflight"
        assert properties["mode"]["enum"] == ["preflight", "full"]

    anyio.run(run)
