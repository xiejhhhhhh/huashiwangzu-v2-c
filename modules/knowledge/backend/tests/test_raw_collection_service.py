"""Tests for raw collection input sanitation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-raw-collection")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from modules.knowledge.backend.services import raw_collection_service


def test_clean_text_for_postgres_strips_nul_bytes() -> None:
    assert raw_collection_service._clean_text_for_postgres("a\x00b\n") == "ab"


def test_clean_json_for_postgres_strips_nested_nul_bytes() -> None:
    payload = {
        "bad\x00key": "hello\x00world",
        "items": [{"text": "x\x00y"}, ("z\x00",)],
    }

    cleaned = raw_collection_service._clean_json_for_postgres(payload)

    assert cleaned == {
        "badkey": "helloworld",
        "items": [{"text": "xy"}, ["z"]],
    }
