import importlib
import os
import sys
from pathlib import Path

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
