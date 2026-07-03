"""Tests for knowledge ingest status contracts."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-ingest-status")

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from modules.knowledge.backend.services.document_service import (
    document_pipeline_complete,
    document_registration_payload,
)
from modules.knowledge.backend.services.ingest_status_service import build_ingest_status_payload


def _doc(**overrides):
    values = {
        "id": 12,
        "owner_id": 1,
        "catalog_id": None,
        "file_id": 99,
        "filename": "sample.txt",
        "extension": "txt",
        "file_size": 128,
        "mime_type": "text/plain",
        "parse_status": "pending",
        "parse_error": None,
        "vector_status": "pending",
        "raw_status": "pending",
        "fusion_status": "pending",
        "total_chunks": 0,
        "total_pages": 0,
        "summary": None,
        "content_package_id": None,
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _task(**overrides):
    values = {
        "id": 77,
        "task_type": "kb_pipeline",
        "status": "pending",
        "retry_count": 0,
        "max_retries": 3,
        "error_message": None,
        "result": None,
        "created_at": None,
        "updated_at": None,
        "started_at": None,
        "completed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_document_registration_payload_exposes_new_task_id() -> None:
    payload = document_registration_payload(
        _doc(),
        {"task_id": 42, "enqueued": True, "reason": "created"},
    )

    assert payload["id"] == 12
    assert payload["document_id"] == 12
    assert payload["task_id"] == 42
    assert payload["enqueued"] is True
    assert payload["reason"] == "created"
    assert payload["stage"] == "kb_pipeline"
    assert payload["status"] == "queued"
    assert payload["search_ready"] is False
    assert payload["deep_ready"] is False


def test_document_registration_payload_marks_existing_inflight() -> None:
    payload = document_registration_payload(
        _doc(),
        {"task_id": 43, "enqueued": False, "reason": "already_in_flight"},
    )

    assert payload["task_id"] == 43
    assert payload["enqueued"] is False
    assert payload["reason"] == "already_in_flight"
    assert payload["status"] == "inflight"


def test_ingest_status_pending_is_not_search_ready() -> None:
    payload = build_ingest_status_payload(_doc(), _task(status="pending"))

    assert payload["task_id"] == 77
    assert payload["task_status"] == "pending"
    assert payload["pipeline_status"] == "queued"
    assert payload["stage"] == "parse"
    assert payload["search_ready"] is False
    assert payload["deep_ready"] is False
    assert payload["next_action"] == "wait_for_search_index"


def test_ingest_status_done_is_search_and_deep_ready() -> None:
    payload = build_ingest_status_payload(
        _doc(
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            total_chunks=8,
            total_pages=2,
        ),
        _task(status="completed", result='{"status":"done"}'),
        profile_count=1,
        graph_entity_count=2,
        relation_count=4,
    )

    assert payload["pipeline_status"] == "deep_ready"
    assert payload["stage"] == "complete"
    assert payload["search_ready"] is True
    assert payload["deep_ready"] is True
    assert payload["stage_summary"]["vector"]["count"] == 8
    assert payload["stage_summary"]["profile"]["ready"] is True
    assert payload["stage_summary"]["graph"]["count"] == 2
    assert payload["next_action"] == "ready"


def test_document_source_missing_marker_blocks_historical_done_readiness() -> None:
    doc = _doc(
        parse_status="done",
        parse_error="source_file_missing",
        vector_status="done",
        raw_status="done",
        fusion_status="done",
        total_chunks=8,
    )

    payload = build_ingest_status_payload(
        doc,
        _task(status="completed", result='{"status":"done"}'),
        profile_count=1,
        graph_entity_count=2,
        relation_count=3,
    )
    registration = document_registration_payload(
        doc,
        {"task_id": None, "enqueued": False, "reason": "not_enqueued"},
    )

    assert document_pipeline_complete(doc) is False
    assert payload["pipeline_status"] == "source_unavailable"
    assert payload["source_available"] is False
    assert payload["source_state"] == "source_file_missing"
    assert payload["last_error"] == "source_file_missing"
    assert payload["search_ready"] is False
    assert payload["deep_ready"] is False
    assert payload["stage_summary"]["parse"]["ready"] is False
    assert payload["stage_summary"]["vector"]["ready"] is False
    assert payload["stage_summary"]["raw"]["ready"] is False
    assert payload["stage_summary"]["fusion"]["ready"] is False
    assert payload["stage_summary"]["profile"]["ready"] is False
    assert payload["stage_summary"]["graph"]["ready"] is False
    assert payload["stage_summary"]["relation"]["ready"] is False
    assert registration["status"] == "source_unavailable"
    assert registration["pipeline_status"] == "source_unavailable"
    assert registration["stage"] == "source"
    assert registration["search_ready"] is False
    assert registration["deep_ready"] is False


def test_ingest_status_graph_ready_can_use_candidate_or_node_counts() -> None:
    payload = build_ingest_status_payload(
        _doc(
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            total_chunks=8,
        ),
        _task(status="completed", result='{"status":"done"}'),
        profile_count=1,
        graph_entity_count=3,
        graph_node_count=5,
        chunk_entity_count=0,
    )

    graph = payload["stage_summary"]["graph"]
    assert graph["ready"] is True
    assert graph["count"] == 3
    assert graph["node_count"] == 5
    assert graph["chunk_entity_count"] == 0


def test_ingest_status_error_surfaces_last_error() -> None:
    payload = build_ingest_status_payload(
        _doc(parse_status="error", parse_error="parser failed"),
        _task(status="failed", error_message="queue failed"),
    )

    assert payload["pipeline_status"] == "failed"
    assert payload["status"] == "failed"
    assert payload["last_error"] == "queue failed"
    assert payload["search_ready"] is False
    assert payload["deep_ready"] is False
    assert payload["next_action"] == "inspect_error_or_retry_pipeline"


def test_ingest_status_degraded_is_explicit() -> None:
    payload = build_ingest_status_payload(
        _doc(
            parse_status="done",
            vector_status="done",
            raw_status="degraded",
            fusion_status="pending",
            total_chunks=8,
        ),
        _task(status="completed", result='{"status":"degraded"}'),
    )

    assert payload["pipeline_status"] == "degraded"
    assert payload["status"] == "degraded"
    assert payload["search_ready"] is True
    assert payload["deep_ready"] is False
    assert payload["next_action"] == "inspect_degraded_or_retry_pipeline"


def test_ingest_status_parser_empty_degraded_can_be_search_ready() -> None:
    payload = build_ingest_status_payload(
        _doc(
            parse_status="degraded",
            parse_error="Parser returned no content blocks: empty_result",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            total_chunks=5,
        ),
        _task(status="completed", result='{"status":"degraded"}'),
    )

    assert payload["pipeline_status"] == "degraded"
    assert payload["stage_summary"]["parse"]["ready"] is True
    assert payload["search_ready"] is True
    assert payload["deep_ready"] is True
    assert payload["last_error"] == "Parser returned no content blocks: empty_result"


def test_ingest_status_source_unavailable_is_not_search_ready() -> None:
    payload = build_ingest_status_payload(
        _doc(
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            total_chunks=8,
        ),
        _task(status="completed", result='{"status":"done"}'),
        source_available=False,
        source_state="source_file_deleted",
    )

    assert payload["pipeline_status"] == "source_unavailable"
    assert payload["status"] == "source_unavailable"
    assert payload["stage"] == "source"
    assert payload["source_available"] is False
    assert payload["source_state"] == "source_file_deleted"
    assert payload["last_error"] == "source_file_deleted"
    assert payload["search_ready"] is False
    assert payload["deep_ready"] is False
    assert payload["stage_summary"]["parse"]["ready"] is False
    assert payload["stage_summary"]["vector"]["ready"] is False
    assert payload["stage_summary"]["raw"]["ready"] is False
    assert payload["stage_summary"]["fusion"]["ready"] is False
    assert payload["next_action"] == "restore_source_or_archive_document"


def test_document_pipeline_complete_accepts_live_source_guard() -> None:
    doc = _doc(
        parse_status="done",
        vector_status="done",
        raw_status="done",
        fusion_status="done",
        total_chunks=8,
    )

    assert document_pipeline_complete(doc) is True
    assert document_pipeline_complete(doc, source_available=True) is True
    assert document_pipeline_complete(doc, source_available=False) is False
