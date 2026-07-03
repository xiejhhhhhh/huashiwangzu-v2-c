from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dev_toolkit import tool_job_tools


def test_tool_job_submit_returns_quickly_and_persists_result(tmp_path: Path) -> None:
    repo_root = tmp_path
    script = repo_root / "dev_toolkit" / "smoke.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "import json\nprint('SMOKE_JSON: ' + json.dumps({'verdict': 'PASS'}))\n",
        encoding="utf-8",
    )

    original_project_python = tool_job_tools._project_python
    tool_job_tools._project_python = lambda _repo_root: sys.executable
    try:
        started = time.monotonic()
        submitted = tool_job_tools.submit_job(repo_root, "smoke_all", {}, "quick smoke")
        assert time.monotonic() - started < 1

        status = {}
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = tool_job_tools.job_status(repo_root, submitted["job_id"])
            if status["status"] in {"completed", "failed", "timeout"}:
                break
            time.sleep(0.05)

        assert status["status"] == "completed"
        assert status["parsed_result"]["verdict"] == "PASS"
        assert "SMOKE_JSON" in status["output_tail"]
        assert Path(status["log_path"]).exists()

        raw_state = json.loads((repo_root / "backend/logs/tool-jobs.json").read_text(encoding="utf-8"))
        assert submitted["job_id"] in raw_state["jobs"]
    finally:
        tool_job_tools._project_python = original_project_python


def test_tool_job_timeout_kills_process_tree(tmp_path: Path) -> None:
    repo_root = tmp_path
    script = repo_root / "dev_toolkit" / "smoke.py"
    marker = repo_root / "backend" / "logs" / "child-marker.txt"
    script.parent.mkdir(parents=True)
    script.write_text(
        "\n".join([
            "import subprocess, sys, time",
            f"marker = {str(marker)!r}",
            "child = subprocess.Popen([sys.executable, '-c', \"import pathlib, time, sys; pathlib.Path(sys.argv[1]).write_text('start'); time.sleep(30)\", marker])",
            "time.sleep(30)",
            "child.wait()",
        ]),
        encoding="utf-8",
    )

    original_project_python = tool_job_tools._project_python
    tool_job_tools._project_python = lambda _repo_root: sys.executable
    try:
        submitted = tool_job_tools.submit_job(repo_root, "smoke_all", {"timeout_seconds": 1}, "timeout smoke")
        status = {}
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            status = tool_job_tools.job_status(repo_root, submitted["job_id"])
            if status["status"] in {"completed", "failed", "timeout"}:
                break
            time.sleep(0.05)

        assert status["status"] == "timeout"
        assert status["timeout"] is True

        time.sleep(1.0)
        if marker.exists():
            mtime_after_timeout = marker.stat().st_mtime_ns
            time.sleep(1.0)
            assert marker.stat().st_mtime_ns == mtime_after_timeout
    finally:
        tool_job_tools._project_python = original_project_python


def test_tool_job_notifications_filters_by_id(tmp_path: Path) -> None:
    tool_job_tools._append_notification(tmp_path, "job_1", "info", "queued")
    tool_job_tools._append_notification(tmp_path, "job_1", "error", "failed")

    result = tool_job_tools.notifications(tmp_path, since_notification_id=1)

    assert result["success"] is True
    assert len(result["notifications"]) == 1
    assert result["notifications"][0]["message"] == "failed"


def test_release_gate_pass_with_debt_is_not_clean_success() -> None:
    output = (
        'RELEASE_GATE_JSON: {"verdict": "PASS_WITH_DEBT", "clean_pass": false, '
        '"release_safe": true, "has_debt": true}\n'
    )

    result = tool_job_tools._parse_result("release_gate", 0, output)

    assert result["success"] is False
    assert result["clean_pass"] is False
    assert result["release_safe"] is True
    assert result["has_debt"] is True


def test_release_gate_pass_with_debt_status_fields_are_explicit(tmp_path: Path) -> None:
    job_id = "job_debt"
    state = {
        "jobs": {
            job_id: {
                "job_id": job_id,
                "tool_name": "release_gate",
                "status": "completed",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "returncode": 0,
                "log_path": str(tmp_path / "backend/logs/tool-jobs/job_debt.log"),
                "parsed_result": {
                    "success": False,
                    "clean_pass": False,
                    "release_safe": True,
                    "has_debt": True,
                    "verdict": "PASS_WITH_DEBT",
                },
            }
        }
    }
    tool_job_tools._write_json_atomic(tool_job_tools._state_path(tmp_path), state)

    status = tool_job_tools.job_status(tmp_path, job_id)

    assert status["status"] == "completed"
    assert status["success"] is False
    assert status["job_success"] is True
    assert status["command_success"] is True
    assert status["clean_success"] is False
    assert status["release_safe"] is True


def test_release_gate_pass_with_debt_notification_is_not_failure(tmp_path: Path) -> None:
    script = tmp_path / "dev_toolkit" / "release_gate.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "print('RELEASE_GATE_JSON: ' + "
        "\"{\\\"verdict\\\": \\\"PASS_WITH_DEBT\\\", \\\"clean_pass\\\": false, "
        "\\\"release_safe\\\": true, \\\"has_debt\\\": true}\")\n",
        encoding="utf-8",
    )

    original_project_python = tool_job_tools._project_python
    tool_job_tools._project_python = lambda _repo_root: sys.executable
    try:
        submitted = tool_job_tools.submit_job(tmp_path, "release_gate", {"mode": "preflight"}, "debt gate")
        deadline = time.monotonic() + 5
        status = {}
        while time.monotonic() < deadline:
            status = tool_job_tools.job_status(tmp_path, submitted["job_id"])
            if status["status"] in {"completed", "failed", "timeout"}:
                break
            time.sleep(0.05)
        notes = tool_job_tools.notifications(tmp_path)["notifications"]
    finally:
        tool_job_tools._project_python = original_project_python

    assert status["status"] == "completed"
    assert status["job_success"] is True
    assert status["clean_success"] is False
    messages = [item["message"] for item in notes]
    assert any("completed with debt" in message for message in messages)
    assert not any("failed" in message for message in messages)


def test_update_job_preserves_existing_fields(tmp_path: Path) -> None:
    first = tool_job_tools._update_job(tmp_path, "job_merge", {"status": "queued", "title": "merge"})
    second = tool_job_tools._update_job(tmp_path, "job_merge", {"pid": 123})

    assert first["status"] == "queued"
    assert second["status"] == "queued"
    assert second["title"] == "merge"
    assert second["pid"] == 123


def test_append_notification_keeps_sequential_ids(tmp_path: Path) -> None:
    for index in range(10):
        tool_job_tools._append_notification(tmp_path, f"job_{index}", "info", f"message {index}")

    notes = tool_job_tools.notifications(tmp_path, limit=20)["notifications"]

    assert [item["id"] for item in notes] == list(range(1, 11))
    assert [item["message"] for item in notes] == [f"message {index}" for index in range(10)]


def test_running_job_with_missing_pid_is_orphaned(tmp_path: Path, monkeypatch) -> None:
    job_id = "job_orphan"
    tool_job_tools._write_json_atomic(
        tool_job_tools._state_path(tmp_path),
        {
            "jobs": {
                job_id: {
                    "job_id": job_id,
                    "status": "running",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "pid": 999999,
                    "log_path": str(tmp_path / "missing.log"),
                }
            }
        },
    )
    monkeypatch.setattr(tool_job_tools, "_pid_exists", lambda _pid: False)

    first = tool_job_tools.job_status(tmp_path, job_id)
    second = tool_job_tools.job_status(tmp_path, job_id)
    notes = tool_job_tools.notifications(tmp_path)["notifications"]

    assert first["stale"] is True
    assert first["orphaned"] is True
    assert "pid 999999" in first["stale_reason"]
    assert second["orphaned"] is True
    assert len([item for item in notes if "stale/orphaned" in item["message"]]) == 1


def test_old_running_job_without_pid_is_stale_not_orphaned(tmp_path: Path) -> None:
    job_id = "job_stale"
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=2000)).isoformat()
    tool_job_tools._write_json_atomic(
        tool_job_tools._state_path(tmp_path),
        {
            "jobs": {
                job_id: {
                    "job_id": job_id,
                    "status": "running",
                    "updated_at": old_time,
                    "timeout_seconds": 10,
                    "log_path": str(tmp_path / "missing.log"),
                }
            }
        },
    )

    status = tool_job_tools.job_status(tmp_path, job_id)

    assert status["stale"] is True
    assert status["orphaned"] is False
    assert "no job state update" in status["stale_reason"]


def test_completed_job_is_not_stale_even_when_old(tmp_path: Path) -> None:
    job_id = "job_done"
    old_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    tool_job_tools._write_json_atomic(
        tool_job_tools._state_path(tmp_path),
        {
            "jobs": {
                job_id: {
                    "job_id": job_id,
                    "status": "completed",
                    "updated_at": old_time,
                    "returncode": 0,
                    "log_path": str(tmp_path / "missing.log"),
                    "parsed_result": {"success": True},
                }
            }
        },
    )

    status = tool_job_tools.job_status(tmp_path, job_id)

    assert status["stale"] is False
    assert status["orphaned"] is False
    assert status["job_success"] is True
