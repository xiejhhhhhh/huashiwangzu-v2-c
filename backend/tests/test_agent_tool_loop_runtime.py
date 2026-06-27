"""Regression tests for ToolLoopRuntime safety helpers."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.agent.backend.engine.stuck_detector import reset
from modules.agent.backend.runtime.tool_loop_runtime import detect_tool_round_stuck
from modules.agent.backend.services.model_client import final_clean_content


def _tool_call(name: str = "search", args: dict | None = None) -> dict:
    return {
        "id": "call_1",
        "type": "function",
        "function": {"name": name, "arguments": args or {"q": "hello"}},
    }


class TestToolRoundStuckDetection:
    def setup_method(self):
        reset("runtime_test")

    def test_same_round_duplicate_calls_count_once(self):
        duplicate_calls = [_tool_call(), _tool_call(), _tool_call()]
        result = detect_tool_round_stuck(duplicate_calls, "runtime_test")
        assert not result["stuck"]

    def test_duplicate_calls_across_rounds_still_trigger(self):
        for _ in range(3):
            result = detect_tool_round_stuck([_tool_call()], "runtime_test")
        assert result["stuck"]


def test_final_event_content_uses_cleaned_text():
    raw = '正文<invoke name="tool"><parameter name="x">1</parameter></invoke>结尾'
    clean_content = final_clean_content(raw)
    pending_event = {"event_type": "assistant_msg", "payload": {"content": clean_content}}
    assert "<invoke" not in pending_event["payload"]["content"]
    assert pending_event["payload"]["content"] == "正文结尾"
