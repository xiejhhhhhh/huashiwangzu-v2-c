from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from dev_toolkit.log_tools import bug_log_files, bug_logs, handle_tool, handles_tool, tool_definitions

pytest.importorskip("mcp")


def test_log_tools_expose_mcp_contract() -> None:
    names = {tool.name for tool in tool_definitions()}

    assert names == {"bug_logs", "bug_log_files"}
    assert handles_tool("bug_logs")
    assert handles_tool("bug_log_files")


def test_bug_logs_finds_recent_errors_and_filters_query(tmp_path: Path) -> None:
    log_dir = tmp_path / "backend" / "logs" / "modules"
    log_dir.mkdir(parents=True)
    (log_dir / "knowledge.log").write_text(
        "\n".join(
            [
                "INFO normal startup",
                "WARNING retrying queue item",
                "ERROR /api/knowledge/documents failed: boom",
                "Traceback (most recent call last):",
                "ValueError: document graph failed",
            ]
        ),
        encoding="utf-8",
    )

    result = bug_logs(tmp_path, query="knowledge", module="knowledge", severity="error", lines=20, limit=5)

    assert result["success"] is True
    assert result["scanned_files"] == 1
    assert any("knowledge/documents" in match["message"] for match in result["matches"])
    assert all(match["path"] == "backend/logs/modules/knowledge.log" for match in result["matches"])


def test_bug_logs_classifies_request_log_as_frontend_source(tmp_path: Path) -> None:
    log_dir = tmp_path / "backend" / "logs" / "modules"
    log_dir.mkdir(parents=True)
    (log_dir / "request.log").write_text(
        "12:00:00 [v2.request] ERROR POST /api/desktop/state 500 9ms\n",
        encoding="utf-8",
    )

    result = bug_logs(tmp_path, query="/api/desktop/state", sources="frontend", severity="error")

    assert result["scanned_files"] == 1
    assert result["matches"][0]["source"] == "frontend"


def test_bug_log_handle_tool_returns_json(tmp_path: Path) -> None:
    log_dir = tmp_path / "backend" / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "backend.log").write_text("CRITICAL backend failed\n", encoding="utf-8")

    payload = json.loads(asyncio.run(handle_tool(tmp_path, "bug_logs", {"sources": "backend"})))

    assert payload["success"] is True
    assert payload["matches"][0]["severity"] == "critical"


def test_bug_log_files_handles_missing_log_dir(tmp_path: Path) -> None:
    result = bug_log_files(tmp_path)

    assert result == {
        "success": True,
        "filters": {
            "sources": ["all"],
            "module": "",
            "include_archived": False,
            "include_empty": False,
        },
        "file_count": 0,
        "files": [],
    }
