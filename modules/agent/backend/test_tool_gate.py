"""Tests for ToolGate — tool call name validation."""

import importlib.util
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[3]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

TOOL_GATE_PATH = REPO_DIR / "modules/agent/backend/runtime/tool_gate.py"
spec = importlib.util.spec_from_file_location("modules.agent.backend.runtime.tool_gate", TOOL_GATE_PATH)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

validate_tool_calls = gate.validate_tool_calls
format_retry_message = gate.format_retry_message


def test_valid_tool_passes():
    tools = [
        {"function": {"name": "knowledge__search"}},
        {"function": {"name": "web-tools__search"}},
    ]
    parsed = [
        {"name": "knowledge__search", "tool_call_id": "1", "args": {}, "slow_name": None},
    ]
    valid, invalid = validate_tool_calls(parsed, tools)
    assert len(valid) == 1
    assert len(invalid) == 0


def test_registered_tool_passes_even_when_not_exposed():
    tools = [
        {"function": {"name": "skill_use"}},
    ]
    parsed = [
        {"name": "knowledge__search", "tool_call_id": "1", "args": {}, "slow_name": None},
    ]
    valid, invalid = validate_tool_calls(parsed, tools, registered_tool_names={"knowledge__search"})
    assert len(valid) == 1
    assert len(invalid) == 0


def test_unregistered_tool_rejected_when_not_exposed():
    tools = [
        {"function": {"name": "skill_use"}},
    ]
    parsed = [
        {"name": "unknown__search", "tool_call_id": "1", "args": {}, "slow_name": None},
    ]
    valid, invalid = validate_tool_calls(parsed, tools, registered_tool_names={"knowledge__search"})
    assert len(valid) == 0
    assert invalid == ["unknown__search"]


def test_invalid_tool_rejected():
    tools = [
        {"function": {"name": "knowledge__search"}},
    ]
    parsed = [
        {"name": "web__request", "tool_call_id": "1", "args": {}, "slow_name": None},
    ]
    valid, invalid = validate_tool_calls(parsed, tools)
    assert len(valid) == 0
    assert invalid == ["web__request"]


def test_skill_use_always_valid():
    tools = [
        {"function": {"name": "knowledge__search"}},
    ]
    parsed = [
        {"name": "skill_use", "tool_call_id": "1", "args": {"name": "web-tools__search"}, "slow_name": None},
    ]
    valid, invalid = validate_tool_calls(parsed, tools)
    assert len(valid) == 1
    assert len(invalid) == 0


def test_mixed_valid_and_invalid():
    tools = [
        {"function": {"name": "knowledge__search"}},
    ]
    parsed = [
        {"name": "knowledge__search", "tool_call_id": "1", "args": {}, "slow_name": None},
        {"name": "web__request", "tool_call_id": "2", "args": {}, "slow_name": None},
        {"name": "web-search__search", "tool_call_id": "3", "args": {}, "slow_name": None},
    ]
    valid, invalid = validate_tool_calls(parsed, tools)
    assert len(valid) == 1
    assert invalid == ["web__request", "web-search__search"]


def test_empty_tools_list():
    tools = []
    parsed = [
        {"name": "knowledge__search", "tool_call_id": "1", "args": {}, "slow_name": None},
    ]
    valid, invalid = validate_tool_calls(parsed, tools)
    assert len(valid) == 0
    assert invalid == ["knowledge__search"]


def test_format_retry_message():
    msg = format_retry_message(["web__request"])
    assert "web__request" in msg
    assert "unregistered" in msg or "invalid" in msg or "not registered" in msg


def test_empty_no_invalid():
    valid, invalid = validate_tool_calls([], [])
    assert len(valid) == 0
    assert len(invalid) == 0
