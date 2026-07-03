from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from dev_toolkit.insight_tools import agent_activity_report, mcp_self_check
from dev_toolkit.tool_usage_tools import empty_tool_usage, write_tool_usage

pytest.importorskip("mcp")

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_mcp_self_check_discovers_components_and_wiring() -> None:
    result = json.loads(mcp_self_check(REPO_ROOT, REPO_ROOT / "backend" / "logs" / "tool_usage_stats.json"))

    assert result["duplicate_tools"] == []
    assert result["orphan_tools"] == []
    assert result["direct_tool_count"] == 0
    assert "brief" in result["tools"]
    assert "batch_quick_fix_apply" in result["tools"]
    assert "mcp_self_check" in result["tools"]
    assert any(component["file"] == "dev_toolkit/core_tools.py" for component in result["components"])
    assert any(component["file"] == "dev_toolkit/edit_tools.py" for component in result["components"])
    assert any(component["file"] == "dev_toolkit/insight_tools.py" for component in result["components"])

    wired = result["wired_components"]
    assert any(w["component"] == "core_tools" and w["wired"] for w in wired)
    assert any(w["component"] == "opencode_tools" and w["wired"] for w in wired)
    assert any(w["component"] == "insight_tools" and w["wired"] for w in wired)


def test_every_tool_component_exposes_contract() -> None:
    for path in sorted((REPO_ROOT / "dev_toolkit").glob("*_tools.py")):
        if path.name.startswith("test_"):
            continue
        module = importlib.import_module(f"dev_toolkit.{path.stem}")
        assert callable(getattr(module, "tool_definitions", None)), path.name
        assert callable(getattr(module, "handles_tool", None)), path.name
        assert callable(getattr(module, "handle_tool", None)), path.name
        tool_names = {tool.name for tool in module.tool_definitions()}
        assert tool_names, path.name
        assert all(module.handles_tool(name) for name in tool_names), path.name


def test_agent_activity_report_reads_feedback_and_usage(tmp_path: Path) -> None:
    memory_dir = tmp_path / "开发文档" / "项目记忆"
    memory_dir.mkdir(parents=True)
    feedback = memory_dir / "feedback.md"
    feedback.write_text(
        "---\n"
        "name: \"反馈\"\n"
        "type: \"reference\"\n"
        "tags: [mcp-feedback, dev-toolkit]\n"
        "agent: \"codex\"\n"
        "created: \"2026-07-02T00:00:00+00:00\"\n"
        "---\n\n"
        "# MCP 使用反馈\n\n"
        "## 任务\n\n测试\n\n"
        "## 顺畅度\n\n- 评分：5/5\n\n"
        "## 本次用到的工具\n\nprobe, code_explore\n\n"
        "## 卡点 / 不顺手的地方\n\n无\n\n"
        "## 缺少的工具 / 能力\n\n无\n\n"
        "## 升级建议\n\n继续升级\n",
        encoding="utf-8",
    )
    usage_path = tmp_path / "backend" / "logs" / "tool_usage_stats.json"
    usage = empty_tool_usage()
    usage["total_calls"] = 1
    usage["agents"] = {"codex": {"calls": 1, "success": 1, "error": 0, "tools": {"probe": 1}}}
    write_tool_usage(usage_path, usage)

    result = json.loads(agent_activity_report(tmp_path, usage_path, agent="codex"))

    codex = result["feedback_by_agent"]["codex"]
    assert codex["feedback_count"] == 1
    assert codex["avg_rating"] == 5
    assert codex["declared_tools"][0] == ["probe", 1]
    assert result["usage_by_agent"]["codex"]["calls"] == 1
