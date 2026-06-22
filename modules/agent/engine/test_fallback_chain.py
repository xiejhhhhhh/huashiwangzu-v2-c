"""Tests for 降级链.py — model fallback chain."""
from unittest.mock import AsyncMock, patch
import pytest
from 降级链 import _extract_reason


class TestExtractReason:
    def test_basic_exception(self):
        e = ValueError("connection refused")
        reason = _extract_reason(e)
        assert "connection refused" in reason

    def test_truncated_message(self):
        e = ValueError("x" * 500)
        reason = _extract_reason(e)
        assert len(reason) <= 310
