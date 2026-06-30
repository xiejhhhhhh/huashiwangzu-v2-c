"""Tests for compressor.py — slide window compression + cheap model summarization."""
from unittest.mock import AsyncMock, patch

import pytest

from . import compressor as compressor_module
from .compressor import (
    _FIRST_COMPRESS_HEAD_COUNT,
    _SUBSEQUENT_COMPRESS_HEAD_COUNT,
    _TAIL_BUDGET_MAX,
    _TAIL_BUDGET_MIN,
    _compute_tail_info,
    _find_tool_pairs,
    _get_last_user_msg_index,
    _select_foldable_indices,
    compress_middle,
)


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


class TestSelectFoldableIndices:
    def test_first_compress_protects_6_head(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(40)]
        selected = _select_foldable_indices(events, generation=0)
        assert min(selected) >= _FIRST_COMPRESS_HEAD_COUNT

    def test_subsequent_compress_protects_2_head(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(40)]
        selected = _select_foldable_indices(events, generation=1)
        assert min(selected) >= _SUBSEQUENT_COMPRESS_HEAD_COUNT

    def test_middle_tool_pair_is_folded_atomically(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(40)]
        events[12] = MockEvent(13, "tool_call", {"id": "call_1", "name": "search", "arguments": {"q": "x"}})
        events[13] = MockEvent(14, "tool_result", {"tool_call_id": "call_1", "result": {"ok": True}})
        selected = set(_select_foldable_indices(events))
        assert {12, 13}.issubset(selected)

    def test_tail_respects_budget(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(50)]
        tail_count, budget = _compute_tail_info(events, history_budget=10000)
        assert tail_count >= 8
        assert _TAIL_BUDGET_MIN <= budget <= _TAIL_BUDGET_MAX

    def test_tail_protects_last_user_msg(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(30)]
        events.append(MockEvent(31, "tool_call", {"name": "test"}))
        events.append(MockEvent(32, "tool_result", {"result": "ok"}))
        last_user = _get_last_user_msg_index(events)
        assert last_user == 29  # 0-indexed, event id 30
        after_last_user = len(events) - last_user - 1  # 32 - 29 - 1 = 2
        tail_count, _ = _compute_tail_info(events, history_budget=48000)
        assert tail_count >= after_last_user


class TestHeadProtection:
    def test_first_compress_protects_6(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(30)]
        selected = _select_foldable_indices(events, generation=0)
        # First 6 should not be in foldable
        assert all(idx >= 6 for idx in selected)

    def test_subsequent_compress_protects_2(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(30)]
        selected = _select_foldable_indices(events, generation=1)
        # First 2 should not be in foldable
        assert all(idx >= 2 for idx in selected)

    def test_already_folded_ids_skipped(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(35)]
        selected = _select_foldable_indices(events, already_folded_ids={11, 12, 13})
        for idx in selected:
            ev = events[idx]
            assert ev.id not in {11, 12, 13}


class TestSmallHistory:
    def test_small_history_skipped_first_compress(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(8)]
        assert len(events) < 20  # small enough
        # This must not result in foldable indices
        foldable = _select_foldable_indices(events, generation=0)
        assert len(foldable) == 0

    def test_small_history_skipped_subsequent_compress(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(4)]
        foldable = _select_foldable_indices(events, generation=1)
        assert len(foldable) == 0


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
            ),
            patch.object(
                compressor_module,
                "record_event",
                new_callable=AsyncMock,
            ) as record,
        ):
            result = await compress_middle(db, 1, events, persist_event=False)

        assert result["status"] == "compressed"
        assert len(result["folded_event_ids"]) > 0
        assert result["summary"] == "complete summary"
        record.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_compress_with_generation_parameter(self):
        events = [MockEvent(i + 1, "user_msg", {"content": f"message-{i}"}) for i in range(35)]
        db = AsyncMock()

        with (
            patch.object(
                compressor_module,
                "_summarize_with_cheap_model",
                new_callable=AsyncMock,
                return_value="complete summary",
            ),
            patch.object(
                compressor_module,
                "record_event",
                new_callable=AsyncMock,
            ),
        ):
            result_gen0 = await compress_middle(db, 1, events, persist_event=False, generation=0)
            result_gen1 = await compress_middle(db, 1, events, persist_event=False, generation=1)

        # gen0 protects 6, gen1 protects 2 — so gen1 should fold more (head=2)
        assert len(result_gen1["folded_event_ids"]) >= len(result_gen0["folded_event_ids"])


class TestSummaryPrefix:
    def test_summary_prefix_constant(self):
        from .compressor import _SUMMARY_PREFIX
        assert "仅供参考" in _SUMMARY_PREFIX
        assert "不是当前指令" in _SUMMARY_PREFIX
        assert _SUMMARY_PREFIX.startswith("[历史摘要")


class TestCompressMiddleSmallHistory:
    @pytest.mark.asyncio
    async def test_too_few_events_skipped(self):
        from .compressor import compress_middle

        events = [MockEvent(i + 1, "user_msg", {"content": f"m{i}"}) for i in range(5)]
        db = AsyncMock()
        result = await compress_middle(db, 1, events, persist_event=False)
        assert result["status"] == "skipped"
