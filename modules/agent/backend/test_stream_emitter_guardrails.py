"""Tests for StreamEmitter guardrails."""

import importlib.util
import sys
import types
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[3]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

engine_module = types.ModuleType("modules.agent.backend.engine.engine")


async def _empty_stream(*_args, **_kwargs):
    if False:
        yield {}


engine_module.chat_stream_with_degradation_chain = _empty_stream
failure_module = types.ModuleType("modules.agent.backend.engine.failure_diagnostics")


async def _record_failure(*_args, **_kwargs):
    return None


failure_module.record_failure = _record_failure
sys.modules["modules.agent.backend.engine.engine"] = engine_module
sys.modules["modules.agent.backend.engine.failure_diagnostics"] = failure_module

STREAM_EMITTER_PATH = REPO_DIR / "modules/agent/backend/runtime/stream_emitter.py"
spec = importlib.util.spec_from_file_location("modules.agent.backend.runtime.stream_emitter", STREAM_EMITTER_PATH)
assert spec and spec.loader
stream_emitter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stream_emitter)
looks_like_unfinished_tool_intent = stream_emitter.looks_like_unfinished_tool_intent
TOOL_INTENT_RETRY_MESSAGE = stream_emitter.TOOL_INTENT_RETRY_MESSAGE


def test_detects_unfinished_search_intent_reply():
    assert looks_like_unfinished_tool_intent("这个问题我帮你联网查一下最新信息。") is True


def test_allows_normal_answer_with_search_context():
    content = "根据搜索结果，巨量千川后台可以在工具里的创意营销榜查看对标视频。"
    assert looks_like_unfinished_tool_intent(content) is False


def test_retry_message_requires_tool_call_or_direct_answer():
    assert "emit the appropriate tool call" in TOOL_INTENT_RETRY_MESSAGE
    assert "answer directly" in TOOL_INTENT_RETRY_MESSAGE
