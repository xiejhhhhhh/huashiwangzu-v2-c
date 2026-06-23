"""Tests for fallback_chain.py — model fallback chain."""
import sys
from pathlib import Path
_MODULES_DIR = str(Path(__file__).resolve().parent.parent.parent)
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from unittest.mock import AsyncMock, patch
import pytest
from agent.engine.fallback_chain import _extract_reason


class TestExtractReason:
    def test_basic_exception(self):
        e = ValueError("connection refused")
        reason = _extract_reason(e)
        assert "connection refused" in reason

    def test_truncated_message(self):
        e = ValueError("x" * 500)
        reason = _extract_reason(e)
        assert len(reason) <= 310
