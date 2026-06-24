"""Tests for event_store.py — string arguments conversion."""
import json
import pytest
from .event_store import _ensure_string_arguments


class TestEnsureStringArguments:
    def test_passes_through_string(self):
        assert _ensure_string_arguments('{"key": "val"}') == '{"key": "val"}'

    def test_converts_dict_to_string(self):
        result = _ensure_string_arguments({"category": "web-tools"})
        assert result == '{"category": "web-tools"}'

    def test_converts_nested_dict(self):
        result = _ensure_string_arguments({"name": "search", "args": {"q": "hello"}})
        parsed = json.loads(result)
        assert parsed["name"] == "search"
        assert parsed["args"]["q"] == "hello"

    def test_empty_dict(self):
        result = _ensure_string_arguments({})
        assert result == "{}"

    def test_empty_string(self):
        assert _ensure_string_arguments("") == ""

    def test_invalid_type_falls_back(self):
        """Non-dict, non-string types get str() fallback."""
        result = _ensure_string_arguments(42)
        assert result == "42"
