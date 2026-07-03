import importlib
import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-pipeline-debt")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


pipeline_debt_service = importlib.import_module("modules.knowledge.backend.services.pipeline_debt_service")


class _Doc:
    id = 1
    file_id = 10
    deleted = False


class _DeletedDoc(_Doc):
    deleted = True


class _File:
    id = 10
    deleted = False


class _DeletedFile(_File):
    deleted = True


class _Run:
    id = 100
    document_id = 1
    file_id = 10
    status = "running"
    started_at = None
    updated_at = None


class _MutableDoc:
    def __init__(self, doc_id: int, file_id: int, *, deleted: bool = False):
        self.id = doc_id
        self.file_id = file_id
        self.deleted = deleted
        self.parse_status = "parsing"
        self.vector_status = "indexing"
        self.raw_status = "collecting"
        self.fusion_status = "fusing"
        self.parse_error = "previous-doc-error"


class _MutableFile:
    def __init__(self, file_id: int, *, deleted: bool = False):
        self.id = file_id
        self.deleted = deleted


class _Task:
    def __init__(
        self,
        task_id: int,
        document_id: int,
        error_message: str,
        *,
        result: str | None = None,
    ):
        self.id = task_id
        self.task_type = "kb_pipeline"
        self.module = "knowledge"
        self.parameters = json.dumps({"document_id": document_id})
        self.status = "failed"
        self.error_message = error_message
        self.result = result
        self.started_at = "started"
        self.completed_at = None
        self.retry_count = 2


class _FakeDb:
    def __init__(self, *, docs: dict[int, _MutableDoc], files: dict[int, _MutableFile]):
        self.docs = docs
        self.files = files
        self.commit_count = 0

    async def get(self, model, row_id: int):
        if model.__name__ == "KbDocument":
            return self.docs.get(row_id)
        if model.__name__ == "File":
            return self.files.get(row_id)
        return None

    async def commit(self) -> None:
        self.commit_count += 1


class _EmptyScalarResult:
    def all(self) -> list:
        return []


class _EmptyExecuteResult:
    def scalars(self) -> _EmptyScalarResult:
        return _EmptyScalarResult()


class _CaptureExecuteDb:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _EmptyExecuteResult()


def test_pipeline_debt_error_family_covers_recent_unmatched_markers():
    assert pipeline_debt_service._classify_error_family("Task result status=failed") == "task_result_failed"
    assert (
        pipeline_debt_service._classify_error_family(
            "greenlet_spawn has not been called; can't call await_only() here."
        )
        == "greenlet_spawn"
    )
    assert (
        pipeline_debt_service._classify_error_family("Document is already parsing")
        == "document_already_parsing"
    )
    assert (
        pipeline_debt_service._classify_error_family("'DocumentIr' object has no attribute 'get'")
        == "document_ir_contract_error"
    )


def test_pipeline_debt_classifies_live_recent_markers_without_lifecycle_mutation():
    live_doc = _Doc()
    live_file = _File()

    category, action, parse_error, family = pipeline_debt_service._classify_task(
        live_doc,
        live_file,
        "greenlet_spawn has not been called",
    )

    assert category == "async_context_error"
    assert action == "code_defect_investigation"
    assert parse_error is None
    assert family == "greenlet_spawn"


def test_pipeline_debt_lifecycle_state_takes_precedence_over_error_marker():
    category, action, parse_error, family = pipeline_debt_service._classify_task(
        _Doc(),
        _DeletedFile(),
        "Task result status=failed",
    )

    assert category == "source_file_deleted"
    assert action == "archive_lifecycle_skip"
    assert parse_error == "source_file_deleted"
    assert family == "task_result_failed"


def test_pipeline_debt_orphan_running_run_classification_is_diagnostic_only():
    category, action, parse_error = pipeline_debt_service._classify_orphan_run(
        _Run(),
        _Doc(),
        None,
    )

    assert category == "orphan_run_source_file_missing"
    assert action == "reconcile_source_unavailable"
    assert parse_error == "source_file_missing"


def test_pipeline_debt_orphan_running_live_run_requests_reconcile():
    category, action, parse_error = pipeline_debt_service._classify_orphan_run(
        _Run(),
        _Doc(),
        _File(),
    )

    assert category == "orphan_run_live_without_task"
    assert action == "reconcile_stale_running_run"
    assert parse_error is None


def test_pipeline_debt_problem_queue_prioritizes_recent_marker_and_orphan_issues():
    queue = pipeline_debt_service._build_problem_queue(
        {
            "summary": {
                "source_file_missing": 2,
                "async_context_error": 6,
                "duplicate_or_stale_parse_lock": 6,
            },
        },
        {"summary": {"orphan_run_source_file_missing": 4}},
        {"summary": {"status_doc_source_file_missing": 12}},
    )

    assert queue[0]["severity"] == "P1"
    assert queue[0]["category"] == "status_doc_source_file_missing"
    assert {item["category"] for item in queue[:4]} >= {
        "async_context_error",
        "duplicate_or_stale_parse_lock",
        "orphan_run_source_file_missing",
    }


@pytest.mark.asyncio
async def test_pipeline_debt_task_ids_are_not_limited():
    db = _CaptureExecuteDb()

    await pipeline_debt_service._load_candidate_tasks(db, limit=1, task_ids=[1, 2, 3])

    assert db.statement is not None
    assert getattr(db.statement, "_limit_clause", None) is None


@pytest.mark.asyncio
async def test_pipeline_debt_unscoped_query_keeps_limit():
    db = _CaptureExecuteDb()

    await pipeline_debt_service._load_candidate_tasks(db, limit=1)

    assert db.statement is not None
    assert getattr(db.statement, "_limit_clause", None) is not None


@pytest.mark.asyncio
async def test_archive_obsolete_only_archives_guarded_lifecycle_categories(monkeypatch):
    docs = {
        1: _MutableDoc(1, 10),
        2: _MutableDoc(2, 20),
        3: _MutableDoc(3, 30, deleted=True),
        4: _MutableDoc(4, 40),
        5: _MutableDoc(5, 50),
        6: _MutableDoc(6, 60),
    }
    files = {
        20: _MutableFile(20, deleted=True),
        40: _MutableFile(40),
        50: _MutableFile(50),
        60: _MutableFile(60),
    }
    tasks = [
        _Task(101, 99, "Document 99 not found", result='{"old": true}'),
        _Task(102, 1, "File not found: /missing.pdf"),
        _Task(103, 2, "Task result status=failed"),
        _Task(104, 3, "Document 3 not found"),
        _Task(105, 4, "Parser returned no content blocks"),
        _Task(106, 5, "greenlet_spawn has not been called"),
        _Task(107, 6, "some transient gateway failure"),
    ]

    async def fake_load_candidate_tasks(db, *, limit=500, error_marker=None, task_ids=None):
        return tasks

    monkeypatch.setattr(
        pipeline_debt_service,
        "_load_candidate_tasks",
        fake_load_candidate_tasks,
    )
    db = _FakeDb(docs=docs, files=files)

    result = await pipeline_debt_service.apply_pipeline_lifecycle_debt_action(
        db,
        action="archive_obsolete",
        dry_run=False,
    )

    assert result["changed"] == 3
    assert result["skipped"] == 4
    assert result["changed_by_category"] == {
        "doc_missing": 1,
        "source_file_missing": 1,
        "source_file_deleted": 1,
    }
    assert result["skipped_by_category"] == {
        "doc_deleted": 1,
        "parser_no_content_blocks": 1,
        "async_context_error": 1,
        "file_row_live": 1,
    }
    assert [task.status for task in tasks[:3]] == ["completed", "completed", "completed"]
    assert [task.status for task in tasks[3:]] == ["failed", "failed", "failed", "failed"]
    assert docs[1].parse_error == "source_file_missing"
    assert docs[2].parse_error == "source_file_deleted"
    assert docs[3].parse_error == "previous-doc-error"
    assert db.commit_count == 1

    archived_payload = json.loads(tasks[0].result or "{}")
    assert archived_payload["status"] == "skipped"
    assert archived_payload["archived_by"] == "knowledge_pipeline_debt_governance"
    assert archived_payload["classification"] == "doc_missing"
    assert archived_payload["reason"] == "doc_missing"
    assert archived_payload["document_id"] == 99
    assert archived_payload["file_id"] is None
    assert archived_payload["previous_error_message"] == "Document 99 not found"
    assert archived_payload["previous_status"] == "failed"
    assert archived_payload["previous_result"] == '{"old": true}'


@pytest.mark.asyncio
async def test_archive_obsolete_dry_run_has_same_shape_without_commit(monkeypatch):
    docs = {1: _MutableDoc(1, 10)}
    tasks = [_Task(201, 1, "File not found: /missing.pdf")]

    async def fake_load_candidate_tasks(db, *, limit=500, error_marker=None, task_ids=None):
        return tasks

    monkeypatch.setattr(
        pipeline_debt_service,
        "_load_candidate_tasks",
        fake_load_candidate_tasks,
    )
    db = _FakeDb(docs=docs, files={})

    result = await pipeline_debt_service.apply_pipeline_lifecycle_debt_action(
        db,
        action="archive_obsolete",
        dry_run=True,
    )

    assert {
        "dry_run",
        "action",
        "matched",
        "changed",
        "skipped",
        "summary",
        "changed_by_category",
        "skipped_by_category",
        "changed_items",
        "skipped_items",
    } <= set(result)
    assert result["changed_by_category"] == {"source_file_missing": 1}
    assert result["skipped_by_category"] == {}
    assert tasks[0].status == "failed"
    assert tasks[0].result is None
    assert docs[1].parse_error == "previous-doc-error"
    assert db.commit_count == 0


@pytest.mark.asyncio
async def test_archive_obsolete_precise_task_ids_apply_all_requested(monkeypatch):
    docs = {
        1: _MutableDoc(1, 10),
        2: _MutableDoc(2, 20),
    }
    tasks = [
        _Task(301, 1, "File not found: /missing-one.pdf"),
        _Task(302, 2, "File not found: /missing-two.pdf"),
    ]
    seen = {}

    async def fake_load_candidate_tasks(db, *, limit=500, error_marker=None, task_ids=None):
        seen["limit"] = limit
        seen["task_ids"] = task_ids
        return tasks

    monkeypatch.setattr(
        pipeline_debt_service,
        "_load_candidate_tasks",
        fake_load_candidate_tasks,
    )
    db = _FakeDb(docs=docs, files={})

    result = await pipeline_debt_service.apply_pipeline_lifecycle_debt_action(
        db,
        action="archive_obsolete",
        limit=1,
        task_ids=[301, 302],
        dry_run=False,
    )

    assert seen == {"limit": 1, "task_ids": [301, 302]}
    assert result["matched"] == 2
    assert result["changed"] == 2
    assert result["changed_by_category"] == {"source_file_missing": 2}
    assert [task.status for task in tasks] == ["completed", "completed"]
