"""Tests for compressor.py — slide window compression + cheap model summarization."""
from unittest.mock import AsyncMock, patch

import pytest

from . import compressor as compressor_module
from .compressor import _find_tool_pairs, _select_foldable_indices, compress_middle


class MockEvent:
    def __init__(self, id, event_type, payload=None, llm_response_id=None):
        self.id = id
        self.event_type = event_type
        self.payload = payload or {}
        self.llm_response_id = llm_response_id


class TestFindToolPairs:
    def test_empty(self):
        assert _find_tool_pairs([]) == []

    def test_no_tool_pairs(self):
        events = [
            MockEvent(1, "user_msg", {"content": "hello"}),
            MockEvent(2, "assistant_msg", {"content": "hi"}),
        ]
        assert _find_tool_pairs(events) == []

    def test_tool_pair_detected(self):
        events = [
            MockEvent(1, "assistant_msg", {"content": ""}, llm_response_id="r1"),
            MockEvent(2, "tool_call", {"name": "search"}, llm_response_id="r1"),
            MockEvent(3, "tool_result", {"result": "data"}, llm_response_id="r1"),
        ]
        pairs = _find_tool_pairs(events)
        assert len(pairs) == 1
        assert pairs[0] == (1, 3)

    def test_multiple_tool_pairs(self):
        events = [
            MockEvent(1, "assistant_msg", {"content": ""}, llm_response_id="r1"),
            MockEvent(2, "tool_call", {"name": "search"}, llm_response_id="r1"),
            MockEvent(3, "tool_result", {"result": "a"}, llm_response_id="r1"),
            MockEvent(4, "assistant_msg", {"content": ""}, llm_response_id="r2"),
            MockEvent(5, "tool_call", {"name": "fetch"}, llm_response_id="r2"),
        ]
        pairs = _find_tool_pairs(events)
        assert len(pairs) == 2


class TestAsyncCompactionPayload:
    def test_middle_tool_pair_is_folded_atomically(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(40)]
        events[12] = MockEvent(13, "tool_call", {"id": "call_1", "name": "search", "arguments": {"q": "x"}})
        events[13] = MockEvent(14, "tool_result", {"tool_call_id": "call_1", "result": {"ok": True}})

        selected = set(_select_foldable_indices(events))

        assert {12, 13}.issubset(selected)

    @pytest.mark.asyncio
    async def test_non_persistent_mode_returns_full_payload_without_event_write(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"message-{i}"}) for i in range(35)]
        db = AsyncMock()

        with (
            patch.object(
                compressor_module,
                "_summarize_with_cheap_model",
                new_callable=AsyncMock,
                return_value="complete summary",
            ) as summarize,
            patch.object(
                compressor_module,
                "record_event",
                new_callable=AsyncMock,
            ) as record,
        ):
            result = await compress_middle(db, 1, events, persist_event=False)

        assert result["status"] == "compressed"
        assert result["folded_event_ids"] == [11, 12, 13, 14, 15]
        assert result["summary"] == "complete summary"
        summary_input = summarize.await_args.args[0]
        assert "message-10" in summary_input
        assert "message-14" in summary_input
        record.assert_not_awaited()
