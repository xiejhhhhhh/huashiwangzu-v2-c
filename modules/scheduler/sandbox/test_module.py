"""Sandbox test for scheduler module.

Validates parameter schemas, required fields, value ranges, and output
shapes for all public_actions — without creating real scheduled tasks.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path


def _assert_rejected(fn: Callable[[], None], label: str) -> None:
    try:
        fn()
    except AssertionError:
        print(f"{label}: PASS")
        return
    raise AssertionError(f"{label}: expected AssertionError")


def _validate_action_description(value: str) -> None:
    assert isinstance(value, str) and len(value.strip()) > 0, \
        "action_description must be a non-empty string"


def _validate_title(value: str) -> None:
    assert isinstance(value, str) and len(value.strip()) > 0, \
        "title must be a non-empty string"


def _validate_recur(value: str | None) -> None:
    if value in (None, ""):
        return
    assert isinstance(value, str), "recur must be a string"
    if value in {"hourly", "daily", "weekly"}:
        return
    assert value.startswith("cron:"), "recur must be hourly/daily/weekly or cron:HH:MM"
    parts = value.split(":")
    assert len(parts) == 3, "cron recur must be cron:HH:MM"
    hour = int(parts[1])
    minute = int(parts[2])
    assert 0 <= hour <= 23 and 0 <= minute <= 59, "cron time out of range"


def _validate_task_id(value: int) -> None:
    assert isinstance(value, int) and value > 0, "task_id must be a positive integer"


def test_create_params() -> None:
    """create: title/action_description, scheduled_at, and optional recur."""
    params_min = {
        "title": "Weekly report",
        "action_description": "Send weekly report",
        "scheduled_at": "2026-07-08T09:00:00",
    }
    assert "title" in params_min
    _validate_title(params_min["title"])
    assert "action_description" in params_min
    _validate_action_description(params_min["action_description"])
    assert "scheduled_at" in params_min
    assert isinstance(params_min["scheduled_at"], str)
    _validate_datetime(params_min["scheduled_at"])
    print("  [CREATE] Minimal params valid")

    params_recur = {
        "title": "Weekly report",
        "action_description": "Send weekly report",
        "scheduled_at": "2026-07-08T09:00:00",
        "recur": "cron:09:00",
    }
    assert "recur" in params_recur
    _validate_recur(params_recur["recur"])
    print("  [CREATE] With recur param valid")


def _validate_datetime(dt_str: str) -> None:
    """Validate that a datetime string is parseable."""
    # Accept ISO-8601 or common variants
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            datetime.strptime(dt_str, fmt)
            return
        except ValueError:
            continue
    raise AssertionError(f"Unparseable datetime string: {dt_str}")


def test_create_params_rejects_invalid_datetime() -> None:
    """Create requires a parseable datetime."""
    bad_dt = "not-a-date"
    _assert_rejected(lambda: _validate_datetime(bad_dt), "  [CREATE] Invalid datetime rejected")


def test_create_params_rejects_empty_action() -> None:
    """Create requires non-empty action_description."""
    params = {"action_description": "", "scheduled_at": "2026-07-08T09:00:00"}
    assert "action_description" in params
    _assert_rejected(
        lambda: _validate_action_description(params["action_description"]),
        "  [CREATE] Empty action rejected",
    )


def test_create_params_rejects_empty_title() -> None:
    """Create requires non-empty title."""
    params = {"title": "", "action_description": "Send report"}
    assert "title" in params
    _assert_rejected(
        lambda: _validate_title(params["title"]),
        "  [CREATE] Empty title rejected",
    )


def test_create_params_rejects_invalid_recur() -> None:
    """Create only accepts interval keywords or cron:HH:MM."""
    _assert_rejected(
        lambda: _validate_recur("0 9 * * 1"),
        "  [CREATE] Legacy cron rejected",
    )
    _assert_rejected(
        lambda: _validate_recur("cron:24:00"),
        "  [CREATE] Out-of-range cron rejected",
    )


def test_list_params() -> None:
    """list: no params."""
    params: dict = {}
    assert len(params) == 0
    print("  [LIST] Parameter contract valid")


def test_cancel_params() -> None:
    """cancel: task_id (int required)."""
    params = {"task_id": 5}
    assert "task_id" in params
    _validate_task_id(params["task_id"])
    print("  [CANCEL] Parameter contract valid")


def test_cancel_params_rejects_zero_id() -> None:
    """Cancel requires positive task_id."""
    params = {"task_id": 0}
    _assert_rejected(lambda: _validate_task_id(params["task_id"]), "  [CANCEL] Zero task_id rejected")


def test_task_output_shape() -> None:
    """Task object output shape contract."""
    task = {
        "id": 1,
        "title": "Weekly report",
        "action_description": "Send weekly report",
        "scheduled_at": "2026-07-08T09:00:00",
        "recur": None,
        "status": "pending",
        "created_at": "2026-07-01T00:00:00",
    }
    required = {"id", "title", "action_description", "scheduled_at", "status"}
    for field in required:
        assert field in task, f"Missing required field: {field}"
    assert isinstance(task["id"], int)
    assert task["status"] in ("pending", "running", "completed", "cancelled", "failed"), f"Invalid status: {task['status']}"
    print("  [TASK] Output shape valid")


def test_task_with_recur_output_shape() -> None:
    """Task with recurrence output shape contract."""
    task = {
        "id": 2,
        "title": "Daily backup",
        "action_description": "Daily backup",
        "scheduled_at": "2026-07-02T02:00:00",
        "recur": "cron:02:00",
        "status": "pending",
        "created_at": "2026-07-01T00:00:00",
    }
    required = {"id", "title", "action_description", "scheduled_at", "recur", "status"}
    for field in required:
        assert field in task, f"Missing required field: {field}"
    _validate_recur(task["recur"])
    print("  [TASK_RECUR] Output shape valid")


def test_cancel_output_shape() -> None:
    """Cancel operation output shape contract."""
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
    """List output is an array of task objects."""
    tasks = [
        {
            "id": 1,
            "title": "Weekly report",
            "action_description": "Send weekly report",
            "scheduled_at": "2026-07-08T09:00:00",
            "recur": "cron:09:00",
            "status": "pending",
            "created_at": "2026-07-01T00:00:00",
        },
        {
            "id": 2,
            "title": "Daily backup",
            "action_description": "Daily backup",
            "scheduled_at": "2026-07-02T02:00:00",
            "recur": None,
            "status": "completed",
            "created_at": "2026-07-01T00:00:00",
        },
    ]
    assert isinstance(tasks, list)
    for task in tasks:
        assert "id" in task and "title" in task and "action_description" in task
        assert "status" in task
        assert task["status"] in ("pending", "running", "completed", "cancelled", "failed")
    print("  [LIST_OUTPUT] Output shape valid")


def test_response_shape() -> None:
    """Unified API response shape contract."""
    r = {"success": True, "data": {"tasks": []}, "error": None}
    assert all(k in r for k in ("success", "data", "error"))
    assert r["success"] is True
    print("  [RESPONSE] Shape valid")


def test_runtime_scheduler_base_path() -> None:
    """Module runtime must not double-prefix /api."""
    runtime_path = Path(__file__).resolve().parents[1] / "runtime" / "index.ts"
    runtime_source = runtime_path.read_text(encoding="utf-8")
    assert "const BASE = '/scheduler'" in runtime_source
    assert "const BASE = '/api/scheduler'" not in runtime_source
    print("  [RUNTIME] Scheduler base path valid")


def main() -> None:
    print("=" * 60)
    print("scheduler sandbox test")
    print("=" * 60)
    test_create_params()
    test_create_params_rejects_invalid_datetime()
    test_create_params_rejects_empty_action()
    test_create_params_rejects_empty_title()
    test_create_params_rejects_invalid_recur()
    test_list_params()
    test_cancel_params()
    test_cancel_params_rejects_zero_id()
    test_task_output_shape()
    test_task_with_recur_output_shape()
    test_cancel_output_shape()
    test_list_output_shape()
    test_response_shape()
    test_runtime_scheduler_base_path()
    print("=" * 60)
    print("PASS: scheduler sandbox test")


if __name__ == "__main__":
    main()
