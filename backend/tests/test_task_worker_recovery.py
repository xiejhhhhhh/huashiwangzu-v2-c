import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.database import AsyncSessionLocal
from app.models.system import SystemTaskQueue
from app.services import task_worker
from sqlalchemy import delete


async def _cleanup(task_type: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(SystemTaskQueue).where(SystemTaskQueue.task_type == task_type))
        await db.commit()


async def _create_task(task_type: str, status: str, started_at: datetime | None = None) -> int:
    async with AsyncSessionLocal() as db:
        task = SystemTaskQueue(
            task_type=task_type,
            parameters=json.dumps({"marker": task_type}),
            status=status,
            priority=0,
            module="test",
            retry_count=0,
            max_retries=3,
            started_at=started_at,
        )
        db.add(task)
        await db.commit()
        return task.id


async def _get_task(task_id: int) -> SystemTaskQueue:
    async with AsyncSessionLocal() as db:
        task = await db.get(SystemTaskQueue, task_id)
        assert task is not None
        return task


@pytest.mark.asyncio
async def test_concurrent_startup_recovery_does_not_reclaim_fresh_running_task() -> None:
    task_type = f"test_fresh_recovery_{uuid4().hex}"
    await _cleanup(task_type)
    try:
        task_id = await _create_task(task_type, "running", datetime.now(timezone.utc))

        await asyncio.gather(*[task_worker._recover_orphan_running_tasks() for _ in range(3)])

        task = await _get_task(task_id)
        assert task.status == "running"
        assert task.retry_count == 0
    finally:
        await _cleanup(task_type)


@pytest.mark.asyncio
async def test_concurrent_startup_recovery_reclaims_stale_running_task_once() -> None:
    task_type = f"test_stale_recovery_{uuid4().hex}"
    await _cleanup(task_type)
    try:
        stale_started_at = datetime.now(timezone.utc) - timedelta(
            seconds=task_worker.RUNNING_TIMEOUT_SECONDS + 60
        )
        task_id = await _create_task(task_type, "running", stale_started_at)

        await asyncio.gather(*[task_worker._recover_orphan_running_tasks() for _ in range(3)])

        task = await _get_task(task_id)
        assert task.status == "pending"
        assert task.retry_count == 1
        assert task.started_at is None
    finally:
        await _cleanup(task_type)


@pytest.mark.asyncio
async def test_handler_semantic_failure_is_not_completed() -> None:
    task_type = f"test_semantic_failure_{uuid4().hex}"
    await _cleanup(task_type)

    async def failing_handler(_parameters: dict) -> dict:
        return {"status": "failed", "error": "boom"}

    previous = task_worker._HANDLERS.get(task_type)
    task_worker.register_task_handler(task_type, failing_handler)
    try:
        task_id = await _create_task(task_type, "running", datetime.now(timezone.utc))
        task = await _get_task(task_id)

        ok, result, error = await task_worker._run_handler(task)
        async with AsyncSessionLocal() as db:
            await task_worker._finish_task(db, task_id, ok, result, error)

        updated = await _get_task(task_id)
        assert updated.status == "pending"
        assert updated.retry_count == 1
        assert updated.error_message == "boom"
    finally:
        if previous is None:
            task_worker._HANDLERS.pop(task_type, None)
        else:
            task_worker._HANDLERS[task_type] = previous
        await _cleanup(task_type)


@pytest.mark.asyncio
async def test_handler_business_dict_completes_normally() -> None:
    task_type = f"test_success_result_{uuid4().hex}"
    await _cleanup(task_type)

    async def success_handler(_parameters: dict) -> dict:
        return {"document_id": 123, "status": "queued"}

    previous = task_worker._HANDLERS.get(task_type)
    task_worker.register_task_handler(task_type, success_handler)
    try:
        task_id = await _create_task(task_type, "running", datetime.now(timezone.utc))
        task = await _get_task(task_id)

        ok, result, error = await task_worker._run_handler(task)
        async with AsyncSessionLocal() as db:
            await task_worker._finish_task(db, task_id, ok, result, error)

        updated = await _get_task(task_id)
        assert updated.status == "completed"
        assert json.loads(updated.result or "{}") == {"document_id": 123, "status": "queued"}
        assert updated.error_message is None
    finally:
        if previous is None:
            task_worker._HANDLERS.pop(task_type, None)
        else:
            task_worker._HANDLERS[task_type] = previous
        await _cleanup(task_type)


def test_worker_health_marks_last_active_as_process_local() -> None:
    health = task_worker.worker_health()

    assert health["process_local"] is True
    assert health["pid"] == os.getpid()
    assert health["last_active_scope"] == "process"
    assert isinstance(health["registered_handlers"], list)
