"""Tests for stuck_detector.py — stuck detection."""
from .stuck_detector import detect_stuck, reset


class TestStuckDetection:
    def setup_method(self):
        reset("test")

    def test_not_stuck_single_call(self):
        result = detect_stuck(tool_name="search", tool_args={"q": "hello"}, error_text=None, is_empty_response=False, session_key="test")
        assert not result["stuck"]

    def test_stuck_same_tool_3_times(self):
        for _ in range(3):
            result = detect_stuck(tool_name="search", tool_args={"q": "hello"}, error_text=None, is_empty_response=False, session_key="test")
        assert result["stuck"]
        assert "search" in result["reason"]

    def test_stuck_same_error_3_times(self):
        for _ in range(3):
            result = detect_stuck(tool_name=None, tool_args=None, error_text="timeout", is_empty_response=False, session_key="test")
        assert result["stuck"]
        assert "timeout" in result["reason"]

    def test_stuck_empty_response_3_times(self):
        for _ in range(3):
            result = detect_stuck(tool_name=None, tool_args=None, error_text=None, is_empty_response=True, session_key="test")
        assert result["stuck"]

    def test_not_stuck_different_tools(self):
        tools = [("search", {"q": "a"}), ("fetch", {"url": "b"}), ("search", {"q": "c"})]
        for name, args in tools:
            result = detect_stuck(tool_name=name, tool_args=args, error_text=None, is_empty_response=False, session_key="test")
        assert not result["stuck"]

    def test_reset_clears_history(self):
        for _ in range(3):
            detect_stuck(tool_name="search", tool_args={"q": "x"}, error_text=None, is_empty_response=False, session_key="test")
        reset("test")
        result = detect_stuck(tool_name="other", tool_args={"q": "y"}, error_text=None, is_empty_response=False, session_key="test")
        assert not result["stuck"]
