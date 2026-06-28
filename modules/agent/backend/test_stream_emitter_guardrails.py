"""Tests for StreamEmitter guardrails.

Note: the guard functions (looks_like_unfinished_tool_intent, TOOL_INTENT_RETRY_MESSAGE)
now live in content_gate.py. We import from there directly to avoid deep import chains.
"""

import importlib.util
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[3]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

CONTENT_GATE_PATH = REPO_DIR / "modules/agent/backend/runtime/content_gate.py"
spec = importlib.util.spec_from_file_location("modules.agent.backend.runtime.content_gate", CONTENT_GATE_PATH)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

looks_like_unfinished_tool_intent = gate.looks_like_unfinished_tool_intent
TOOL_INTENT_RETRY_MESSAGE = gate.TOOL_INTENT_RETRY_MESSAGE


def test_detects_unfinished_search_intent_reply():
    assert looks_like_unfinished_tool_intent("这个问题我帮你联网查一下最新信息。") is True


def test_allows_normal_answer_with_search_context():
    content = "根据搜索结果，巨量千川后台可以在工具里的创意营销榜查看对标视频。"
    assert looks_like_unfinished_tool_intent(content) is False


def test_retry_message_requires_tool_call_or_direct_answer():
    assert "emit the appropriate tool call" in TOOL_INTENT_RETRY_MESSAGE
    assert "answer directly" in TOOL_INTENT_RETRY_MESSAGE
