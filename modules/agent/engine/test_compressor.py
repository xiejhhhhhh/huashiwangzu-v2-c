"""Tests for 压缩器.py — slide window compression + cheap model summarization."""
import pytest
from unittest.mock import AsyncMock, patch
from 压缩器 import _find_tool_pairs


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
