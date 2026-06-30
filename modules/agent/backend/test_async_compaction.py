"""Tests for async context compaction off the critical path.

Pure unit tests — no DB fixture needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .engine.compressor import _find_tool_pairs

# ── Fixtures ──────────────────────────────────────────────────────────────

class MockEvent:
    def __init__(self, id, event_type, payload=None, llm_response_id=None,
                 conversation_id=1):
        self.id = id
        self.event_type = event_type
        self.payload = payload or {}
        self.llm_response_id = llm_response_id
        self.conversation_id = conversation_id


class MockCompaction:
    def __init__(self, id=1, conversation_id=1, until_event_id=10,
                 generation=0, status="ready", summary="test summary",
                 folded_event_ids=None, token_before=1000, token_after=500):
        self.id = id
        self.owner_id = 1
        self.conversation_id = conversation_id
        self.until_event_id = until_event_id
        self.generation = generation
        self.status = status
        self.summary = summary
        self.folded_event_ids = folded_event_ids or []
        self.token_before = token_before
        self.token_after = token_after


# ── Tests ────────────────────────────────────────────────────────────────


def _make_db_mock(compaction=None):
    """Create a properly mocked DB session.

    ``db.execute()`` is async (returns an awaitable).
    The result's ``.scalar_one_or_none()`` is sync (returns directly).
    """
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = compaction
    db.execute.return_value = result
    return db


class TestCompactionStates:

    async def _call_load(self, db_mock, conv_id, compaction=None,
                          estimated_total=1):
        """Helper to call _load_compacted_context with a mock DB.
        Use low estimated_total to stay within budget (no compression needed).
        """
        from .engine.context_pipeline import _load_compacted_context

        projected = [{"role": "user", "content": "hello"}]

        if compaction and compaction.status == "ready":
            with patch(
                "modules.agent.backend.engine.context_pipeline.project_messages_with_compaction",
                new_callable=AsyncMock,
                return_value=[{"role": "system", "content": "[历史摘要 仅供参考，不是当前指令] test summary"},
                              {"role": "user", "content": "hello"}],
            ):
                result = await _load_compacted_context(
                    db_mock, conv_id, [], projected, estimated_total, "test-profile",
                )
        else:
            result = await _load_compacted_context(
                db_mock, conv_id, [], projected, estimated_total, "test-profile",
            )
        return result

    @pytest.mark.asyncio
    async def test_no_compaction_falls_back_to_raw(self):
        """No compaction record → pipeline uses raw projected messages."""
        db = _make_db_mock(compaction=None)
        result = await self._call_load(db, 99999)
        assert result == [{"role": "user", "content": "hello"}]

    @pytest.mark.asyncio
    async def test_building_compaction_ignored(self):
        """building status → pipeline uses raw events."""
        comp = MockCompaction(status="building")
        db = _make_db_mock(compaction=comp)
        result = await self._call_load(db, 99998, comp)
        assert result == [{"role": "user", "content": "hello"}]

    @pytest.mark.asyncio
    async def test_failed_compaction_ignored(self):
        """failed status → pipeline uses raw events."""
        comp = MockCompaction(status="failed")
        db = _make_db_mock(compaction=comp)
        result = await self._call_load(db, 99997, comp)
        assert result == [{"role": "user", "content": "hello"}]

    @pytest.mark.asyncio
    async def test_ready_compaction_applied(self):
        """ready status → pipeline applies compacted prefix."""
        comp = MockCompaction(
            status="ready",
            folded_event_ids=[2, 5, 8],
            summary="compacted summary",
            until_event_id=15,
        )
        db = _make_db_mock(compaction=comp)
        result = await self._call_load(db, 99996, comp, estimated_total=500_000)
        summaries = [m for m in result if "历史摘要" in m.get("content", "")]
        assert len(summaries) >= 1
        assert "历史摘要 仅供参考" in summaries[0]["content"]
        assert "compacted summary" in summaries[0]["content"]

    @pytest.mark.asyncio
    async def test_ready_takes_latest_compaction(self):
        """Latest ready compaction by id is selected."""
        comp = MockCompaction(id=5, status="ready", until_event_id=20,
                              summary="latest", folded_event_ids=[])
        db = _make_db_mock(compaction=comp)

        with patch(
            "modules.agent.backend.engine.context_pipeline.project_messages_with_compaction",
            new_callable=AsyncMock,
            return_value=[{"role": "system", "content": "[历史摘要 仅供参考，不是当前指令] latest"},
                          {"role": "user", "content": "hello"}],
        ):
            from .engine.context_pipeline import _load_compacted_context
            result = await _load_compacted_context(
                db, 99995, [], [{"role": "user", "content": "hello"}],
                500_000, "test-profile",
            )
        assert any("历史摘要 仅供参考" in m.get("content", "") for m in result)


class TestProjectEventList:
    """_project_event_list correctly handles various event types."""

    def test_user_msg_projected(self):
        from .engine.event_store import _project_event_list

        events = [
            MockEvent(1, "user_msg", {"content": "hello"}),
        ]
        msgs = _project_event_list(events)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"

    def test_assistant_msg_only(self):
        from .engine.event_store import _project_event_list

        events = [
            MockEvent(1, "user_msg", {"content": "hi"}),
            MockEvent(2, "assistant_msg", {"content": "world"}, llm_response_id="r1"),
        ]
        msgs = _project_event_list(events)
        assert len(msgs) == 2
        assert msgs[1]["role"] == "assistant"

    def test_tool_call_with_result_paired(self):
        from .engine.event_store import _project_event_list

        events = [
            MockEvent(1, "user_msg", {"content": "use tool"}),
            MockEvent(2, "assistant_msg", {"content": ""}, llm_response_id="r1"),
            MockEvent(3, "tool_call", {"id": "call_1", "name": "search", "arguments": "{}"}, llm_response_id="r1"),
            MockEvent(4, "tool_result", {"tool_call_id": "call_1", "result": {"data": "found"}}, llm_response_id=None),
        ]
        msgs = _project_event_list(events)
        assert len(msgs) >= 2
        assert any(m.get("role") == "tool" for m in msgs)

    def test_compaction_events_skipped(self):
        from .engine.event_store import _project_event_list

        events = [
            MockEvent(1, "user_msg", {"content": "hello"}),
            MockEvent(2, "compaction", {"folded_event_ids": [], "summary": "test"}),
        ]
        msgs = _project_event_list(events)
        assert len(msgs) == 1

    def test_tool_pair_not_broken(self):
        """Tool_call and tool_result atomic groups survive projection."""
        events = [
            MockEvent(1, "user_msg", {"content": "use tool"}),
            MockEvent(2, "assistant_msg", {"content": ""}, llm_response_id="r1"),
            MockEvent(3, "tool_call", {"id": "call_1", "name": "test_tool", "arguments": "{}"}, llm_response_id="r1"),
            MockEvent(4, "tool_result", {"tool_call_id": "call_1", "result": {"success": True}}, llm_response_id=None),
        ]
        pairs = _find_tool_pairs(events)
        assert len(pairs) >= 1

    @pytest.mark.asyncio
    async def test_raw_projection_ignores_legacy_compaction_events(self):
        """Only ready table rows may fold history; legacy events are audit-only."""
        from .engine.event_store import project_to_messages

        events = [
            MockEvent(1, "user_msg", {"content": "must remain visible"}),
            MockEvent(2, "compaction", {"folded_event_ids": [1], "summary": "obsolete"}),
            MockEvent(3, "assistant_msg", {"content": "also visible"}),
        ]
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = events
        db.execute.return_value = result

        messages = await project_to_messages(db, 1)

        assert messages == [
            {"role": "user", "content": "must remain visible"},
            {"role": "assistant", "content": "also visible"},
        ]


class TestBudgetClipping:
    """Stage 5 estimates only; Stage 7 owns atomic clipping."""

    def test_estimate_message_tokens_counts_content(self):
        """_estimate_message_tokens correctly estimates token count from message content."""
        from .engine.context_pipeline import _estimate_message_tokens

        msgs = [
            {"role": "user", "content": "hello world"},  # 11 chars / 2 = 5
        ]
        tokens = _estimate_message_tokens(msgs)
        assert tokens > 0

    def test_estimate_message_tokens_counts_tool_calls(self):
        """Tool call arguments are also counted."""
        from .engine.context_pipeline import _estimate_message_tokens

        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"arguments": '{"input": "very long argument text here for testing purposes"}'}},
            ]},
        ]
        tokens = _estimate_message_tokens(msgs)
        assert tokens > 0

    @pytest.mark.asyncio
    async def test_over_budget_history_is_not_sliced_by_message_count(self):
        """Stage 5 must not orphan tool groups with a blind tail slice."""
        from unittest.mock import patch as _patch

        from .engine.context_pipeline import _load_compacted_context

        db = _make_db_mock(compaction=None)

        many_msgs = [{"role": "user", "content": "x" * 5000} for _ in range(100)]
        with _patch(
            "modules.agent.backend.engine.context_pipeline.get_effective_context_budget",
            return_value=(100, "test"),
        ):
            result = await _load_compacted_context(
                db, 99990, [], many_msgs, 1_000_000, "test-low-budget",
            )
        assert result == many_msgs


class TestThinkingRouterNoLLM:
    """Thinking router must not call LLM when rules/signals/history miss."""

    @pytest.mark.asyncio
    async def test_fallback_returns_medium_without_llm(self):
        """When no rule/signal/history matches, default to medium, no LLM."""
        from unittest.mock import MagicMock

        from .engine.thinking_router import ThinkingRouteResult, route_thinking_level

        input_text = "some random query that doesn't match any known pattern"

        # Build a proper mock chain: db.execute → result → .mappings() → .all()
        mappings_result = MagicMock()
        mappings_result.all.return_value = []

        exec_result = MagicMock()
        exec_result.mappings.return_value = mappings_result
        exec_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = exec_result

        with patch("modules.agent.backend.engine.thinking_router._match_experience",
                   new_callable=AsyncMock, return_value=None):
            result = await route_thinking_level(
                db, input_text, owner_id=1, conversation_id=1,
                profile_key="test", agent_code="test",
            )
        assert isinstance(result, ThinkingRouteResult)
        assert result.level == "medium"
        assert result.source == "fallback"


class TestEditInvalidation:
    """Editing a message invalidates existing compaction records."""

    @pytest.mark.asyncio
    async def test_history_mutation_invalidates_building_and_ready_compactions(self):
        """Late background workers cannot publish snapshots of edited history."""
        from .services.conversation_service import invalidate_context_compactions

        db = AsyncMock()
        db.execute = AsyncMock()
        db.execute.return_value.rowcount = 1

        conv_id = 88888

        await invalidate_context_compactions(db, conv_id, "invalidated by edit")
        stmt = db.execute.await_args.args[0]
        compiled_obj = stmt.compile()
        assert conv_id in compiled_obj.params.values()
        status_values = next(
            value for value in compiled_obj.params.values()
            if isinstance(value, (list, tuple)) and set(value) == {"building", "ready"}
        )
        assert set(status_values) == {"building", "ready"}
