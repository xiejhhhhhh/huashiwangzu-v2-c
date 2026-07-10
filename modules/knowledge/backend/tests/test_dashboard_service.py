from types import SimpleNamespace

from modules.knowledge.backend.services.dashboard_service import (
    _document_bucket,
    _stage_statuses,
    _task_display_status,
)


def _doc(**overrides):
    values = {
        "raw_status": "pending",
        "fusion_status": "pending",
        "profile_status": "pending",
        "graph_status": "pending",
        "relation_status": "pending",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_pending_document_is_waiting_not_skipped():
    statuses = _stage_statuses(_doc(), None, None)

    assert _document_bucket(statuses, None, None, source_available=True) == "waiting"


def test_pending_paused_task_is_paused():
    task = SimpleNamespace(
        id=10,
        status="pending",
        stage_key="graph",
        lane_key="model_analysis",
        ready_status="ready",
    )
    task_status = _task_display_status(task, {"graph"}, set())
    statuses = _stage_statuses(_doc(raw_status="done", fusion_status="done", profile_status="done"), task, task_status)

    assert task_status == "paused"
    assert statuses["graph_status"] == "paused"
    assert _document_bucket(statuses, task, task_status, source_available=True) == "paused"


def test_latest_failed_task_is_failed_even_if_stage_still_pending():
    task = SimpleNamespace(
        id=11,
        status="failed",
        stage_key="relations",
        lane_key="relation_build",
        ready_status="ready",
    )
    task_status = _task_display_status(task, set(), set())
    statuses = _stage_statuses(_doc(raw_status="done", fusion_status="done", profile_status="done", graph_status="done"), task, task_status)

    assert task_status == "failed"
    assert statuses["relation_status"] == "failed"
    assert _document_bucket(statuses, task, task_status, source_available=True) == "failed"
