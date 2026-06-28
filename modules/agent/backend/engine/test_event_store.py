"""Tests for event_store.py — string arguments conversion."""
import json
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[4]
BACKEND_DIR = REPO_DIR / "backend"
for path in (REPO_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from .event_store import _collect_complete_tool_results, _ensure_string_arguments


class FakeEvent:
    def __init__(self, event_type: str, payload: dict):
        self.event_type = event_type
        self.payload = payload


class TestCollectCompleteToolResults:
    def test_complete_results_for_all_tool_calls(self):
        events = [
            FakeEvent("tool_result", {"tool_call_id": "call_a", "result": {"ok": 1}}),
            FakeEvent("tool_result", {"tool_call_id": "call_b", "result": {"ok": 2}}),
        ]
        results, next_index, complete = _collect_complete_tool_results(events, 0, {"call_a", "call_b"})
        assert complete is True
        assert next_index == 2
        assert len(results) == 2

    def test_partial_results_are_not_complete(self):
        events = [
            FakeEvent("tool_result", {"tool_call_id": "call_a", "result": {"ok": 1}}),
        ]
        results, next_index, complete = _collect_complete_tool_results(events, 0, {"call_a", "call_b"})
        assert complete is False
        assert next_index == 1
        assert len(results) == 1

    def test_unrelated_result_stops_collection(self):
        events = [
            FakeEvent("tool_result", {"tool_call_id": "call_a", "result": {"ok": 1}}),
            FakeEvent("tool_result", {"tool_call_id": "other", "result": {"ok": 2}}),
        ]
        results, next_index, complete = _collect_complete_tool_results(events, 0, {"call_a", "call_b"})
        assert complete is False
        assert next_index == 1
        assert len(results) == 1


class TestEnsureStringArguments:
    def test_passes_through_string(self):
        assert _ensure_string_arguments('{"key": "val"}') == '{"key": "val"}'

    def test_converts_dict_to_string(self):
        result = _ensure_string_arguments({"category": "web-tools"})
        assert result == '{"category": "web-tools"}'

    def test_converts_nested_dict(self):
        result = _ensure_string_arguments({"name": "search", "args": {"q": "hello"}})
        parsed = json.loads(result)
        assert parsed["name"] == "search"
        assert parsed["args"]["q"] == "hello"

    def test_empty_dict(self):
        result = _ensure_string_arguments({})
        assert result == "{}"

    def test_empty_string(self):
        assert _ensure_string_arguments("") == ""

    def test_invalid_type_falls_back(self):
        """Non-dict, non-string types get str() fallback."""
        result = _ensure_string_arguments(42)
        assert result == "42"
