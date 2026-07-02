import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _load_raw_service():
    for module_name, module in sys.modules.items():
        if module_name.endswith(".raw_collection_service") and hasattr(module, "collect_raw_data"):
            return module
    return importlib.import_module("modules.knowledge.backend.services.raw_collection_service")


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def all(self):
        return []


class _FakeDocument:
    id = 123
    extension = "txt"
    total_pages = 1
    raw_status = "pending"


class _FakeDb:
    def __init__(self):
        self.doc = _FakeDocument()
        self.commits = 0

    async def execute(self, _stmt):
        return _ScalarResult(self.doc)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


class _SessionFactory:
    def __init__(self, db):
        self.db = db

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc_info):
        return None


@pytest.mark.asyncio
async def test_collect_raw_data_marks_failed_when_all_rounds_return_errors(monkeypatch):
    raw_service = _load_raw_service()

    async def fake_round_1(*_args, **_kwargs):
        return {"round": 1, "page": 1, "chars": 0, "error": "parser failed"}

    monkeypatch.setattr(raw_service, "_exec_round_1_text", fake_round_1)
    monkeypatch.setattr(raw_service, "AsyncSessionLocal", _SessionFactory(_FakeDb()))

    db = _FakeDb()
    result = await raw_service.collect_raw_data(
        db,
        doc_id=123,
        owner_id=1,
        file_id=456,
        user_id=1,
    )

    assert result["status"] == "failed"
    assert db.doc.raw_status == "failed"
