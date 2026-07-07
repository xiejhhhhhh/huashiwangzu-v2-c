import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.database import AsyncSessionLocal
from app.models.system import SystemTaskQueue
from app.services import task_worker
from sqlalchemy import delete


def test_task_worker_treats_skipped_as_successful_noop() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "status": "skipped",
        "reason": "source_file_deleted",
    })

    assert failed is False
    assert error is None


def test_task_worker_treats_failed_status_as_failure() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "status": "failed",
        "error": "slow tool failed",
    })

    assert failed is True
    assert error == "slow tool failed"


def test_task_worker_treats_failed_reason_as_failure_detail() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "status": "failed",
        "reason": "LibreOffice conversion timed out",
    })

    assert failed is True
    assert error == "LibreOffice conversion timed out"


def test_task_worker_treats_success_false_as_failure() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "success": False,
        "error": "agent execution failed",
    })

    assert failed is True
    assert error == "agent execution failed"


def test_task_worker_treats_nested_success_false_as_failure() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "success": True,
        "data": {"success": False, "error": "nested failed"},
    })

    assert failed is True
    assert error == "nested failed"


def test_task_worker_treats_legacy_code_nonzero_as_failure() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "code": 1,
        "msg": "legacy tool failed",
    })

    assert failed is True
    assert error == "legacy tool failed"


def test_task_worker_config_defaults_are_safe() -> None:
    config = task_worker._parse_worker_config({})

    assert config.worker_lanes_per_process == 1
    assert config.max_lanes_per_process == task_worker.DEFAULT_MAX_LANES_PER_PROCESS
    assert config.worker_process_mode == "leader"
    assert config.worker_process_slots == 1
    assert config.claim_lock_scope == "process"
    assert config.poll_interval_seconds == 2.0
    assert config.running_timeout_seconds == 1200
    assert config.config_reload_seconds == 5.0
    assert config.reclaim_running_on_startup is False
    assert config.startup_reclaim_min_age_seconds == 10
    assert config.claim_candidate_scan_limit == 100
    assert config.stage_concurrency == {}
    assert config.lane_concurrency == {}


def test_task_worker_config_clamps_lane_count() -> None:
    config = task_worker._parse_worker_config({
        "worker_lanes_per_process": 999,
        "max_lanes_per_process": 24,
        "worker_process_mode": "all",
        "worker_process_slots": 3,
        "claim_lock_scope": "database",
        "poll_interval_seconds": 0,
        "running_timeout_seconds": 1,
        "config_reload_seconds": 0,
        "reclaim_running_on_startup": "true",
        "startup_reclaim_min_age_seconds": -1,
    })

    assert config.worker_lanes_per_process == 24
    assert config.max_lanes_per_process == 24
    assert config.worker_process_mode == "all"
    assert config.worker_process_slots == 3
    assert config.claim_lock_scope == "database"
    assert config.poll_interval_seconds == 0.2
    assert config.running_timeout_seconds == 60
    assert config.config_reload_seconds == 1.0
    assert config.reclaim_running_on_startup is True
    assert config.startup_reclaim_min_age_seconds == 0


def test_task_worker_config_allows_zero_lanes_for_hot_pause() -> None:
    config = task_worker._parse_worker_config({"worker_lanes_per_process": 0})

    assert config.worker_lanes_per_process == 0


def test_task_worker_config_derives_no_claim_lock_when_claims_not_serialized() -> None:
    config = task_worker._parse_worker_config({"serialize_claims": False})

    assert config.serialize_claims is False
    assert config.claim_lock_scope == "none"


def test_task_worker_config_rejects_unknown_process_and_claim_modes() -> None:
    config = task_worker._parse_worker_config({
        "worker_process_mode": "everything",
        "claim_lock_scope": "globalish",
    })

    assert config.worker_process_mode == "leader"
    assert config.claim_lock_scope == "process"


def test_task_worker_config_clamps_dynamic_max_lanes() -> None:
    config = task_worker._parse_worker_config({
        "worker_lanes_per_process": 999,
        "max_lanes_per_process": 999,
    })

    assert config.worker_lanes_per_process == task_worker.ABSOLUTE_MAX_LANES_PER_PROCESS
    assert config.max_lanes_per_process == task_worker.ABSOLUTE_MAX_LANES_PER_PROCESS


def test_task_worker_config_parses_explicit_stage_concurrency() -> None:
    config = task_worker._parse_worker_config({
        "claim_candidate_scan_limit": 9999,
        "stage_concurrency": {
            "kb_pipeline_stage": {
                "parse_index": 28,
                "raw_ocr": 8,
                "raw_vision": 4,
                "bad": 0,
                "too_high": 999,
            },
        },
    })

    assert config.claim_candidate_scan_limit == 5000
    rule = (config.stage_concurrency or {})["kb_pipeline_stage"]
    assert rule.stage_max_running == {
        "parse_index": 28,
        "raw_ocr": 8,
        "raw_vision": 4,
        "too_high": task_worker.ABSOLUTE_MAX_LANES_PER_PROCESS,
    }


def test_task_worker_config_parses_explicit_lane_concurrency() -> None:
    config = task_worker._parse_worker_config({
        "lane_concurrency": {
            "kb_pipeline_stage": {
                "local_preprocess": 72,
                "model_analysis": 96,
                "bad": 0,
                "too_high": 999,
            },
        },
    })

    assert config.lane_concurrency == {
        "kb_pipeline_stage": {
            "local_preprocess": 72,
            "model_analysis": 96,
            "too_high": task_worker.ABSOLUTE_MAX_LANES_PER_PROCESS,
        },
    }


def _queue_task(stage: str, *, status: str = "running", task_type: str = "kb_pipeline_stage") -> SystemTaskQueue:
    return SystemTaskQueue(
        task_type=task_type,
        module="knowledge",
        status=status,
        parameters=json.dumps({"stage": stage}),
        stage_key=stage,
    )


def test_task_worker_stage_concurrency_blocks_only_full_stage() -> None:
    config = task_worker._parse_worker_config({
        "worker_lanes_per_process": 32,
        "max_lanes_per_process": 48,
        "stage_concurrency": {
            "kb_pipeline_stage": {
                "raw_vision": 1,
                "fusion": 2,
                "raw_ocr": 8,
            },
        },
    })
    rules = config.stage_concurrency or {}
    running_counts = task_worker._stage_running_counts(
        [_queue_task("raw_vision"), _queue_task("profile")],
        rules,
    )

    assert task_worker._task_allowed_by_stage_concurrency(
        _queue_task("raw_vision", status="pending"),
        running_counts=running_counts,
        config=config,
    ) is False
    assert task_worker._task_allowed_by_stage_concurrency(
        _queue_task("fusion", status="pending"),
        running_counts=running_counts,
        config=config,
    ) is True
    assert task_worker._task_allowed_by_stage_concurrency(
        _queue_task("raw_ocr", status="pending"),
        running_counts=running_counts,
        config=config,
    ) is True


def test_task_worker_stage_concurrency_requires_configured_stage() -> None:
    config = task_worker._parse_worker_config({
        "stage_concurrency": {
            "kb_pipeline_stage": {
                "raw_vision": 1,
            },
        },
    })
    legacy_json_only_task = SystemTaskQueue(
        task_type="kb_pipeline_stage",
        module="knowledge",
        status="running",
        parameters=json.dumps({"stage": "raw_vision"}),
    )

    counts = task_worker._stage_running_counts(
        [legacy_json_only_task],
        config.stage_concurrency or {},
    )

    assert counts == {}
    assert task_worker._task_allowed_by_stage_concurrency(
        _queue_task("raw_vision", status="pending"),
        running_counts=counts,
        config=config,
    ) is True
    assert task_worker._task_allowed_by_stage_concurrency(
        _queue_task("unconfigured_stage", status="pending"),
        running_counts=counts,
        config=config,
    ) is False


def test_task_worker_lane_concurrency_blocks_only_full_lane() -> None:
    config = task_worker._parse_worker_config({
        "lane_concurrency": {
            "kb_pipeline_stage": {
                "local_preprocess": 1,
                "model_analysis": 8,
            },
        },
    })
    running_task = _queue_task("parse_index")
    running_task.lane_key = "local_preprocess"
    counts = task_worker._lane_running_counts(
        [running_task],
        config.lane_concurrency or {},
    )

    local_task = _queue_task("raw_text", status="pending")
    local_task.lane_key = "local_preprocess"
    model_task = _queue_task("profile", status="pending")
    model_task.lane_key = "model_analysis"

    assert task_worker._task_allowed_by_lane_concurrency(
        local_task,
        lane_running_counts=counts,
        config=config,
    ) is False
    assert task_worker._task_allowed_by_lane_concurrency(
        model_task,
        lane_running_counts=counts,
        config=config,
    ) is True


@pytest.mark.asyncio
async def test_task_worker_stage_concurrency_claims_fair_stage_not_global_priority() -> None:
    task_type = f"test_stage_fair_{uuid4().hex}"
    hot_stage = "local_hot"
    model_stage = "model_ready"
    config = task_worker._parse_worker_config({
        "claim_lock_scope": "process",
        "claim_candidate_scan_limit": 1,
        "stage_concurrency": {
            task_type: {
                hot_stage: 40,
                model_stage: 64,
            },
        },
    })

    async with AsyncSessionLocal() as db:
        try:
            for _ in range(39):
                db.add(SystemTaskQueue(
                    task_type=task_type,
                    module="test",
                    status="running",
                    priority=99,
                    parameters=json.dumps({"stage": hot_stage}),
                    stage_key=hot_stage,
                    ready_status="ready",
                    started_at=datetime.now(timezone.utc),
                ))
            for _ in range(5):
                db.add(SystemTaskQueue(
                    task_type=task_type,
                    module="test",
                    status="pending",
                    priority=99,
                    parameters=json.dumps({"stage": hot_stage}),
                    stage_key=hot_stage,
                    ready_status="ready",
                ))
            expected = SystemTaskQueue(
                task_type=task_type,
                module="test",
                status="pending",
                priority=1,
                parameters=json.dumps({"stage": model_stage}),
                stage_key=model_stage,
                ready_status="ready",
            )
            db.add(expected)
            await db.commit()

            claimed = await task_worker._claim_one_task(db, config)

            assert claimed is not None
            assert claimed.stage_key == model_stage
            assert claimed.id == expected.id
        finally:
            await db.execute(delete(SystemTaskQueue).where(SystemTaskQueue.task_type == task_type))
            await db.commit()


@pytest.mark.asyncio
async def test_task_worker_lane_concurrency_claims_model_when_local_lane_is_full() -> None:
    task_type = f"test_lane_fair_{uuid4().hex}"
    local_stage = "parse_index"
    model_stage = "profile"
    config = task_worker._parse_worker_config({
        "claim_lock_scope": "process",
        "stage_concurrency": {
            task_type: {
                local_stage: 40,
                model_stage: 64,
            },
        },
        "lane_concurrency": {
            task_type: {
                "local_preprocess": 1,
                "model_analysis": 64,
            },
        },
    })

    async with AsyncSessionLocal() as db:
        try:
            db.add(SystemTaskQueue(
                task_type=task_type,
                module="test",
                status="running",
                priority=99,
                parameters=json.dumps({"stage": local_stage}),
                stage_key=local_stage,
                lane_key="local_preprocess",
                ready_status="ready",
                started_at=datetime.now(timezone.utc),
            ))
            db.add(SystemTaskQueue(
                task_type=task_type,
                module="test",
                status="pending",
                priority=99,
                parameters=json.dumps({"stage": local_stage}),
                stage_key=local_stage,
                lane_key="local_preprocess",
                ready_status="ready",
            ))
            expected = SystemTaskQueue(
                task_type=task_type,
                module="test",
                status="pending",
                priority=1,
                parameters=json.dumps({"stage": model_stage}),
                stage_key=model_stage,
                lane_key="model_analysis",
                ready_status="ready",
            )
            db.add(expected)
            await db.commit()

            claimed = await task_worker._claim_one_task(db, config)

            assert claimed is not None
            assert claimed.stage_key == model_stage
            assert claimed.lane_key == "model_analysis"
            assert claimed.id == expected.id
        finally:
            await db.execute(delete(SystemTaskQueue).where(SystemTaskQueue.task_type == task_type))
            await db.commit()


def test_task_worker_handler_uses_explicit_queue_fields_over_parameters() -> None:
    seen = {}

    async def handler(params: dict) -> dict:
        seen.update(params)
        return {"status": "done"}

    original = dict(task_worker._HANDLERS)
    try:
        task_worker.register_task_handler("kb_pipeline_stage", handler)
        task = SystemTaskQueue(
            id=9001,
            task_type="kb_pipeline_stage",
            module="knowledge",
            status="running",
            parameters=json.dumps({
                "document_id": 111,
                "stage": "legacy_wrong_stage",
                "task_id": 1,
            }),
            document_id=222,
            stage_key="raw_vision",
            lane_key="model_analysis",
            dependency_key="knowledge:222:raw_vision",
        )

        ok, result, error = asyncio.run(task_worker._run_handler(task))

        assert ok is True
        assert result == {"status": "done"}
        assert error is None
        assert seen["document_id"] == 222
        assert seen["stage"] == "raw_vision"
        assert seen["task_id"] == 9001
        assert seen["lane"] == "model_analysis"
        assert seen["dependency_key"] == "knowledge:222:raw_vision"
    finally:
        task_worker._HANDLERS.clear()
        task_worker._HANDLERS.update(original)


def test_task_worker_result_serializer_handles_datetime() -> None:
    serialized = task_worker._serialize_task_result({
        "status": "done",
        "completed_at": datetime(2026, 7, 7, 1, 30, tzinfo=timezone.utc),
    })

    assert serialized is not None
    assert '"status": "done"' in serialized
    assert "2026-07-07 01:30:00+00:00" in serialized


def test_active_task_snapshot_is_stable_and_sorted() -> None:
    original = dict(task_worker._lane_current_task_ids)
    try:
        task_worker._lane_current_task_ids.clear()
        task_worker._lane_current_task_ids.update({3: 200, 1: 100, 2: 100})

        assert task_worker._active_task_ids_snapshot() == [100, 200]
    finally:
        task_worker._lane_current_task_ids.clear()
        task_worker._lane_current_task_ids.update(original)
