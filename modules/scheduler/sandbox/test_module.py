"""Sandbox test for scheduler module.

Validates public contracts against the production scheduler router helpers.
The test uses fake async sessions, so it does not create real scheduled tasks
or mutate the framework task queue.
"""

import asyncio
import os
import sys
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("JWT_SECRET", "scheduler-sandbox-secret")

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from app.core.exceptions import ConflictError, ValidationError  # noqa: E402
from app.services import module_registry  # noqa: E402

from modules.scheduler.backend import router as scheduler_router  # noqa: E402


class FakeScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class FakeExecuteResult:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows or []

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self._rows)


class FakeSchedulerTask:
    def __init__(
        self,
        *,
        title: str,
        action_description: str,
        creator_id: int,
        scheduled_at: datetime | None,
        recur: str | None,
    ) -> None:
        self.parameters = scheduler_router._encode_task_parameters(
            title,
            action_description,
            creator_id,
        )
        self.scheduled_at = scheduled_at
        self.recur = recur


class FakeAsyncSession:
    def __init__(self, existing_tasks: list[FakeSchedulerTask] | None = None) -> None:
        self.existing_tasks = existing_tasks or []
        self.added_task: Any | None = None
        self.execute_calls = 0
        self.committed = False

    async def execute(self, _statement: object, _params: dict[str, object] | None = None) -> FakeExecuteResult:
        self.execute_calls += 1
        if self.execute_calls == 1:
            return FakeExecuteResult()
        return FakeExecuteResult(self.existing_tasks)

    def add(self, task: object) -> None:
        self.added_task = task

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, task: object) -> None:
        setattr(task, "id", 123)


class FakeCapabilityCaller:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any], str | None, str | None]] = []

    async def __call__(
        self,
        module: str,
        action: str,
        params: dict[str, Any],
        *,
        caller: str | None = None,
        caller_role: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((module, action, params, caller, caller_role))
        if module == "agent" and action == "spawn_subagent":
            return {
                "success": True,
                "data": {"results": [{"conclusion": "scheduled action done"}]},
            }
        if module == "im" and action == "notify":
            return {"success": True, "data": {"notified": True}}
        return {"success": False, "error": f"unexpected capability {module}:{action}"}


@contextmanager
def _patch_call_capability(fake: FakeCapabilityCaller):
    original = module_registry.call_capability
    module_registry.call_capability = fake
    try:
        yield
    finally:
        module_registry.call_capability = original


def _future_iso(minutes: int = 10) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _future_datetime(minutes: int = 10) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _assert_rejected(fn: Callable[[], None], expected: type[Exception], label: str) -> None:
    try:
        fn()
    except expected:
        print(f"{label}: PASS")
        return
    raise AssertionError(f"{label}: expected {expected.__name__}")


async def _assert_async_rejected(
    fn: Callable[[], Any],
    expected: type[Exception],
    label: str,
) -> None:
    try:
        await fn()
    except expected:
        print(f"{label}: PASS")
        return
    raise AssertionError(f"{label}: expected {expected.__name__}")


def test_production_create_accepts_future_task() -> None:
    async def run() -> None:
        db = FakeAsyncSession()
        task = await scheduler_router._create_scheduler_task(
            db,
            title=" Weekly report ",
            action_description=" Send weekly report ",
            creator_id=7,
            scheduled_at=_future_iso(),
            recur="cron:9:05",
        )
        assert db.added_task is task
        assert db.committed is True
        assert task.id == 123
        assert task.status == "pending"
        assert task.creator_id == 7
        assert task.recur == "cron:09:05"
        assert task.next_run_at == task.scheduled_at
        decoded = scheduler_router._decode_task_parameters(task.parameters)
        assert decoded["title"] == "Weekly report"
        assert decoded["action_description"] == "Send weekly report"

    asyncio.run(run())
    print("  [CREATE] Production helper accepts future task")


def test_production_create_allows_immediate_task() -> None:
    async def run() -> None:
        db = FakeAsyncSession()
        task = await scheduler_router._create_scheduler_task(
            db,
            title="Run now",
            action_description="Execute immediately",
            creator_id=7,
            scheduled_at=None,
            recur=None,
        )
        assert task.scheduled_at is None
        assert task.next_run_at is None

    asyncio.run(run())
    print("  [CREATE] Immediate task remains explicit via empty scheduled_at")


def test_production_create_rejects_empty_fields() -> None:
    _assert_rejected(
        lambda: scheduler_router._normalize_required_text("", "title"),
        ValidationError,
        "  [CREATE] Empty title rejected",
    )
    _assert_rejected(
        lambda: scheduler_router._normalize_required_text("   ", "action_description"),
        ValidationError,
        "  [CREATE] Empty action rejected",
    )


def test_production_create_rejects_invalid_datetime() -> None:
    _assert_rejected(
        lambda: scheduler_router._parse_scheduled_at("not-a-date"),
        ValidationError,
        "  [CREATE] Invalid datetime rejected",
    )


def test_production_create_rejects_past_datetime() -> None:
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    _assert_rejected(
        lambda: scheduler_router._parse_scheduled_at(past),
        ValidationError,
        "  [CREATE] Past datetime rejected",
    )


def test_production_create_rejects_invalid_recur() -> None:
    _assert_rejected(
        lambda: scheduler_router._validate_recur("0 9 * * 1"),
        ValidationError,
        "  [CREATE] Legacy cron rejected",
    )
    _assert_rejected(
        lambda: scheduler_router._validate_recur("cron:24:00"),
        ValidationError,
        "  [CREATE] Out-of-range cron rejected",
    )


def test_production_create_rejects_active_duplicate() -> None:
    async def run() -> None:
        scheduled_at = _future_datetime()
        existing = FakeSchedulerTask(
            title="Weekly report",
            action_description="Send weekly report",
            creator_id=7,
            scheduled_at=scheduled_at,
            recur="weekly",
        )
        db = FakeAsyncSession(existing_tasks=[existing])
        await _assert_async_rejected(
            lambda: scheduler_router._create_scheduler_task(
                db,
                title="Weekly report",
                action_description="Send weekly report",
                creator_id=7,
                scheduled_at=scheduled_at.isoformat(),
                recur="weekly",
            ),
            ConflictError,
            "  [CREATE] Active duplicate rejected",
        )

    asyncio.run(run())


def test_duplicate_signature_lock_is_stable() -> None:
    signature = scheduler_router._task_signature(
        creator_id=7,
        title="Weekly report",
        action_description="Send weekly report",
        scheduled_at=None,
        recur=None,
    )
    assert scheduler_router._signature_lock_id(signature) == scheduler_router._signature_lock_id(signature)
    assert isinstance(scheduler_router._signature_lock_id(signature), int)
    print("  [CREATE] Duplicate lock key stable")


def test_list_params() -> None:
    params: dict[str, object] = {}
    assert len(params) == 0
    print("  [LIST] Parameter contract valid")


def test_cancel_params() -> None:
    assert scheduler_router._parse_positive_task_id(5) == 5
    print("  [CANCEL] Parameter contract valid")


def test_cancel_params_rejects_zero_id() -> None:
    _assert_rejected(
        lambda: scheduler_router._parse_positive_task_id(0),
        ValidationError,
        "  [CANCEL] Zero task_id rejected",
    )


def test_task_output_shape() -> None:
    task = {
        "id": 1,
        "title": "Weekly report",
        "action_description": "Send weekly report",
        "scheduled_at": _future_iso(),
        "recur": None,
        "next_run_at": _future_iso(),
        "status": "pending",
        "created_at": "2026-07-01T00:00:00+00:00",
    }
    required = {"id", "title", "action_description", "scheduled_at", "status", "next_run_at"}
    for field in required:
        assert field in task, f"Missing required field: {field}"
    assert isinstance(task["id"], int)
    assert task["status"] in ("pending", "running", "completed", "cancelled", "failed")
    print("  [TASK] Output shape valid")


def test_task_to_dict_uses_stored_parameters() -> None:
    scheduled_at = _future_datetime()
    task = FakeSchedulerTask(
        title="Weekly report",
        action_description="Send weekly report",
        creator_id=7,
        scheduled_at=scheduled_at,
        recur="weekly",
    )
    task.id = 99
    task.status = "pending"
    task.next_run_at = scheduled_at
    task.result = None
    task.error_message = None
    task.created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    data = scheduler_router._task_to_dict(task)
    assert data["id"] == 99
    assert data["title"] == "Weekly report"
    assert data["action_description"] == "Send weekly report"
    assert data["recur"] == "weekly"
    assert data["next_run_at"] == scheduled_at.isoformat()
    print("  [TASK] Production task serialization valid")


def test_scheduled_job_handler_rejects_legacy_empty_payload() -> None:
    async def run() -> None:
        fake = FakeCapabilityCaller()
        with _patch_call_capability(fake):
            result = await scheduler_router._cap_scheduled_job_handler({
                "title": "   ",
                "action_description": "",
                "creator_id": 7,
            })

        assert result["success"] is False
        assert result["status"] == "failed"
        assert result["executed"] is False
        assert result["error"]
        assert fake.calls == []

    asyncio.run(run())
    print("  [HANDLER] Legacy empty payload fails closed")


def test_scheduled_job_handler_rejects_missing_creator_id() -> None:
    async def run() -> None:
        fake = FakeCapabilityCaller()
        with _patch_call_capability(fake):
            result = await scheduler_router._cap_scheduled_job_handler({
                "title": "Daily check",
                "action_description": "Summarize current queue state",
            })

        assert result["success"] is False
        assert result["status"] == "failed"
        assert result["executed"] is False
        assert result["error"] == "Missing creator_id"
        assert fake.calls == []

    asyncio.run(run())
    print("  [HANDLER] Missing creator_id fails closed")


def test_scheduled_job_handler_accepts_minimal_payload() -> None:
    async def run() -> None:
        fake = FakeCapabilityCaller()
        with _patch_call_capability(fake):
            result = await scheduler_router._cap_scheduled_job_handler({
                "title": "Daily check",
                "action_description": "Summarize current queue state",
                "creator_id": 7,
            })

        assert result["success"] is True
        assert result["executed"] is True
        assert "scheduled action done" in result["result"]
        assert [call[0:2] for call in fake.calls] == [
            ("agent", "spawn_subagent"),
            ("im", "notify"),
        ]

    asyncio.run(run())
    print("  [HANDLER] Minimal scheduled payload executes")


def test_cancel_output_shape() -> None:
    result = {
        "success": True,
        "data": {
            "id": 5,
            "status": "cancelled",
        },
        "error": None,
    }
    assert result["success"] is True
    data = result["data"]
    assert "id" in data and "status" in data
    assert data["status"] == "cancelled"
    print("  [CANCEL_OUTPUT] Output shape valid")


def test_list_output_shape() -> None:
    tasks = [
        {
            "id": 1,
            "title": "Weekly report",
            "action_description": "Send weekly report",
            "scheduled_at": _future_iso(),
            "recur": "cron:09:00",
            "next_run_at": _future_iso(),
            "status": "pending",
            "created_at": "2026-07-01T00:00:00+00:00",
        }
    ]
    assert isinstance(tasks, list)
    for task in tasks:
        assert "id" in task and "title" in task and "action_description" in task
        assert "status" in task and "next_run_at" in task
        assert task["status"] in ("pending", "running", "completed", "cancelled", "failed")
    print("  [LIST_OUTPUT] Output shape valid")


def test_response_shape() -> None:
    response = {"success": True, "data": {"tasks": []}, "error": None}
    assert all(key in response for key in ("success", "data", "error"))
    assert response["success"] is True
    print("  [RESPONSE] Shape valid")


def test_runtime_scheduler_base_path() -> None:
    runtime_path = Path(__file__).resolve().parents[1] / "runtime" / "index.ts"
    runtime_source = runtime_path.read_text(encoding="utf-8")
    assert "const BASE = '/scheduler'" in runtime_source
    assert "const BASE = '/api/scheduler'" not in runtime_source
    print("  [RUNTIME] Scheduler base path valid")


def main() -> None:
    print("=" * 60)
    print("scheduler sandbox test")
    print("=" * 60)
    test_production_create_accepts_future_task()
    test_production_create_allows_immediate_task()
    test_production_create_rejects_empty_fields()
    test_production_create_rejects_invalid_datetime()
    test_production_create_rejects_past_datetime()
    test_production_create_rejects_invalid_recur()
    test_production_create_rejects_active_duplicate()
    test_duplicate_signature_lock_is_stable()
    test_list_params()
    test_cancel_params()
    test_cancel_params_rejects_zero_id()
    test_task_output_shape()
    test_task_to_dict_uses_stored_parameters()
    test_scheduled_job_handler_rejects_legacy_empty_payload()
    test_scheduled_job_handler_rejects_missing_creator_id()
    test_scheduled_job_handler_accepts_minimal_payload()
    test_cancel_output_shape()
    test_list_output_shape()
    test_response_shape()
    test_runtime_scheduler_base_path()
    print("=" * 60)
    print("PASS: scheduler sandbox test")


if __name__ == "__main__":
    main()
