"""Focused tests for codemap feedback stats and capability handlers."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"
for candidate in (PROJECT_ROOT, BACKEND_ROOT):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from modules.codemap.backend import feedback_summary
from modules.codemap.backend import router as router_module
from modules.codemap.backend.locks import lock_router as lock_router_module


def test_empirical_accuracy_is_unknown_without_feedback() -> None:
    fields = feedback_summary.build_empirical_accuracy_fields(query_count=42, feedback_count=0)

    assert fields["empirical_accuracy"] is None
    assert fields["empirical_accuracy_status"] == "no_feedback"
    assert "不能视为 100% 准确" in fields["empirical_accuracy_note"]


def test_empirical_accuracy_uses_feedback_when_available() -> None:
    fields = feedback_summary.build_empirical_accuracy_fields(query_count=20, feedback_count=3)

    assert fields["empirical_accuracy"] == 85
    assert fields["empirical_accuracy_status"] == "measured"
    assert fields["empirical_accuracy_note"] is None


def test_list_feedback_empty_metadata_is_visible() -> None:
    metadata = feedback_summary.build_feedback_list_metadata(
        feedback_count=0,
        page=1,
        page_size=50,
        aggregated_by_path=True,
        path_count=0,
    )

    assert metadata["has_feedback"] is False
    assert metadata["feedback_count"] == 0
    assert metadata["path_count"] == 0
    assert "empirical_accuracy 未知" in metadata["empty_note"]


def test_manifest_public_actions_match_registered_capabilities() -> None:
    manifest = json.loads((PROJECT_ROOT / "modules" / "codemap" / "manifest.json").read_text(encoding="utf-8"))
    router_source = (PROJECT_ROOT / "modules" / "codemap" / "backend" / "router.py").read_text(encoding="utf-8")
    registered = set(re.findall(r'register_capability\(\s*"codemap",\s*"([^"]+)"', router_source))
    public_actions = {entry["action"]: set(entry.get("parameters", {})) for entry in manifest["public_actions"]}

    assert set(public_actions) == registered
    assert {"path", "agent_id", "ttl"} <= public_actions["acquire_lock"]
    assert {"path", "query_type", "codemap_said", "actual", "reason", "agent_id"} <= public_actions[
        "report_inaccuracy"
    ]
    assert {"path", "page", "page_size"} <= public_actions["list_feedback"]


class _FakeScalarResult:
    def __init__(self, value: int) -> None:
        self._value = value

    def scalar(self) -> int:
        return self._value


class _FakeRowsResult:
    def __init__(self, rows: list[tuple[str, int]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, int]]:
        return self._rows


class _FakeScalars:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _FakeScalarsResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _FakeFeedbackDb:
    def __init__(self, store: list[object]) -> None:
        self.store = store

    async def __aenter__(self) -> "_FakeFeedbackDb":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def add(self, feedback: object) -> None:
        feedback.id = len(self.store) + 1
        feedback.created_at = datetime.now(timezone.utc)
        self.store.append(feedback)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def execute(self, statement: object) -> object:
        sql = str(statement)
        if "GROUP BY" in sql:
            counts: dict[str, int] = {}
            for item in self.store:
                counts[item.path] = counts.get(item.path, 0) + 1
            return _FakeRowsResult(sorted(counts.items()))
        if "count(distinct" in sql.lower():
            return _FakeScalarResult(len({item.path for item in self.store}))
        if "count(" in sql.lower():
            return _FakeScalarResult(len(self.store))
        return _FakeScalarsResult(list(self.store))


class _FakeSessionFactory:
    def __init__(self, store: list[object]) -> None:
        self.store = store

    def __call__(self) -> _FakeFeedbackDb:
        return _FakeFeedbackDb(self.store)


@pytest.mark.asyncio
async def test_report_inaccuracy_and_list_feedback_capabilities(monkeypatch) -> None:
    store: list[object] = []

    async def _noop_ensure_tables(db: object) -> None:
        return None

    monkeypatch.setattr(router_module, "AsyncSessionLocal", _FakeSessionFactory(store))
    monkeypatch.setattr(router_module, "_ensure_tables_once", _noop_ensure_tables)

    report = await router_module._cap_report_inaccuracy(
        {
            "path": "./modules//codemap/README.md/",
            "query_type": " verification ",
            "codemap_said": "no reverse edge",
            "actual": "reverse edge exists",
            "reason": "temporary test feedback",
            "agent_id": "codemap-test",
        },
        "user:1",
    )

    assert report["success"] is True
    assert report["data"]["id"] == 1

    listed = await router_module._cap_list_feedback(
        {"path": "modules/codemap/README.md"},
        "user:1",
    )

    assert listed["success"] is True
    data = listed["data"]
    assert data["has_feedback"] is True
    assert data["feedback_count"] == 1
    assert data["aggregated_by_path"] is False
    assert data["items"][0]["path"] == "modules/codemap/README.md"
    assert data["items"][0]["codemap_said"] == "no reverse edge"
    assert data["items"][0]["actual"] == "reverse edge exists"


@pytest.mark.asyncio
async def test_http_list_feedback_empty_state_metadata(monkeypatch) -> None:
    async def _noop_ensure_tables(db: object) -> None:
        return None

    monkeypatch.setattr(lock_router_module, "ensure_codemap_tables", _noop_ensure_tables)

    response = await lock_router_module.http_list_feedback(
        path=None,
        page=1,
        page_size=50,
        db=_FakeFeedbackDb([]),
        _user=object(),
    )

    data = response.data
    assert data["items"] == []
    assert data["has_feedback"] is False
    assert data["feedback_count"] == 0
    assert data["path_count"] == 0
    assert data["aggregated_by_path"] is True
    assert "不能视为 100% 准确" in data["empty_note"]
