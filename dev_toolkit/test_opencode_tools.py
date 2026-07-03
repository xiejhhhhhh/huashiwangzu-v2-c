from __future__ import annotations

from pathlib import Path

import pytest

from dev_toolkit import opencode_queue, opencode_tools


def _make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "华世王镞_v2"
    (repo_root / "backend" / "logs").mkdir(parents=True)
    outbox = tmp_path / opencode_tools.MAILBOX_NAME / "投递箱"
    outbox.mkdir(parents=True)
    return repo_root


def test_list_letters_reads_mailbox_outbox(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    letter = tmp_path / opencode_tools.MAILBOX_NAME / "投递箱" / "审计修复-test.md"
    letter.write_text("# task\n", encoding="utf-8")

    result = opencode_tools.list_letters(repo_root)

    assert result["success"] is True
    assert result["count"] == 1
    assert result["letters"][0]["name"] == "审计修复-test.md"


def test_dispatch_rejects_letter_outside_outbox(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("# nope\n", encoding="utf-8")

    with pytest.raises(ValueError, match="inside mailbox outbox"):
        opencode_tools._resolve_letter(repo_root, str(outside))


def test_dispatch_letter_builds_attached_run_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    letter = tmp_path / opencode_tools.MAILBOX_NAME / "投递箱" / "审计修复-test.md"
    letter.write_text("# task\n", encoding="utf-8")

    monkeypatch.setattr(opencode_tools, "_opencode_binary", lambda: "/bin/echo")
    monkeypatch.setattr(opencode_tools, "_is_listening", lambda *_args, **_kwargs: True)

    result = opencode_tools.dispatch_letter(
        repo_root,
        letter=letter.name,
        title="dispatch test",
        background=False,
        timeout_seconds=10,
    )

    assert result["success"] is True
    assert result["background"] is False
    assert "--attach http://127.0.0.1:55891" in result["stdout"]
    assert str(letter) in result["stdout"]
    assert Path(result["log_path"]).exists()


def test_dispatch_letter_background_closes_stdin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    letter = tmp_path / opencode_tools.MAILBOX_NAME / "投递箱" / "审计修复-test.md"
    letter.write_text("# task\n", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 12345

        def poll(self) -> int | None:
            return None

    def fake_popen(*args: object, **kwargs: object) -> FakeProcess:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(opencode_tools, "_opencode_binary", lambda: "/bin/opencode")
    monkeypatch.setattr(opencode_tools, "_opencode_version", lambda _binary=None: "test")
    monkeypatch.setattr(opencode_tools, "_is_listening", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(opencode_tools, "_listener_pid", lambda _port: None)
    monkeypatch.setattr(opencode_tools.subprocess, "Popen", fake_popen)

    result = opencode_tools.dispatch_letter(repo_root, letter=letter.name, background=True)

    assert result["success"] is True
    assert captured["kwargs"]["stdin"] is opencode_tools.subprocess.DEVNULL


def test_serve_command_does_not_wrap_with_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opencode_tools.shutil, "which", lambda name: "/usr/bin/script" if name == "script" else None)

    command = opencode_tools._serve_command("/bin/opencode", "127.0.0.1", 55891)

    assert command == [
        "/bin/opencode",
        "serve",
        "--hostname",
        "127.0.0.1",
        "--port",
        "55891",
    ]


def test_sdk_tools_are_registered() -> None:
    names = {tool.name for tool in opencode_tools.tool_definitions()}

    assert "opencode_sdk_smoke" in names
    assert "opencode_sdk_prompt" in names
    assert "opencode_sdk_dispatch_letter" in names
    assert "opencode_sdk_messages" in names
    assert "opencode_sdk_job_submit" in names
    assert "opencode_sdk_job_dispatch_letter" in names
    assert "opencode_sdk_job_status" in names
    assert "opencode_sdk_job_list" in names
    assert "opencode_sdk_job_continue" in names
    assert "opencode_sdk_job_notifications" in names
    assert opencode_tools.handles_tool("opencode_sdk_prompt") is True
    assert opencode_tools.handles_tool("opencode_sdk_job_submit") is True
    assert opencode_tools.handles_tool("opencode_sdk_job_notifications") is True


def test_opencode_queue_does_not_complete_async_placeholder() -> None:
    messages = [
        {
            "role": "assistant",
            "cost": 0,
            "tokens": {"input": 0, "output": 0},
            "text": "",
            "parts": [],
        },
    ]

    assert opencode_queue._is_completed(messages) is False


def test_opencode_queue_completes_on_finish_signal() -> None:
    finish_message = [{"role": "assistant", "finish": "stop", "text": "DONE", "parts": []}]
    step_finish_message = [{"role": "assistant", "text": "", "parts": [{"type": "step-finish"}]}]

    assert opencode_queue._is_completed(finish_message) is True
    assert opencode_queue._is_completed(step_finish_message) is True


def test_opencode_queue_monitor_lock_rejects_parallel_worker(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)

    with opencode_queue._job_monitor_lock(repo_root, "ocjob_lock") as first_acquired:
        assert first_acquired is True
        with opencode_queue._job_monitor_lock(repo_root, "ocjob_lock") as second_acquired:
            assert second_acquired is False

    with opencode_queue._job_monitor_lock(repo_root, "ocjob_lock") as reacquired:
        assert reacquired is True


def test_opencode_queue_resumes_existing_session_without_resubmitting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = _make_repo(tmp_path)
    job_id = "ocjob_resume"
    opencode_queue._save_state(
        repo_root,
        {
            "version": 1,
            "jobs": {
                job_id: {
                    "id": job_id,
                    "type": "prompt",
                    "title": "resume",
                    "status": "running",
                    "host": opencode_queue.DEFAULT_HOST,
                    "port": opencode_queue.DEFAULT_PORT,
                    "session_id": "ses_resume",
                    "created_at": "2026-07-03T00:00:00+00:00",
                    "updated_at": "2026-07-03T00:00:00+00:00",
                    "payload": {"action": "prompt_async", "prompt": "original"},
                    "poll_seconds": 1,
                    "stall_seconds": 20,
                    "max_continue": 1,
                    "continue_count": 0,
                    "max_runtime_seconds": 120,
                    "message_limit": 50,
                },
            },
        },
    )

    def fail_if_initial_prompt_is_reposted(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("existing session should be refreshed, not resubmitted")

    monkeypatch.setattr(opencode_queue, "_run_sdk", fail_if_initial_prompt_is_reposted)
    monkeypatch.setattr(
        opencode_queue,
        "_refresh_messages",
        lambda *_args, **_kwargs: {
            "success": True,
            "messages": [{"role": "assistant", "finish": "stop", "text": "DONE", "parts": []}],
        },
    )

    opencode_queue._worker(repo_root, job_id)
    job = opencode_queue.get_job(repo_root, job_id, refresh=False)["job"]

    assert job["status"] == "completed"
    assert job["final_text"] == "DONE"


def test_opencode_queue_creates_terminal_notification_once(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    job_id = "ocjob_notify"
    opencode_queue._save_state(
        repo_root,
        {
            "version": 1,
            "jobs": {
                job_id: {
                    "id": job_id,
                    "type": "prompt",
                    "title": "notify",
                    "status": "running",
                    "created_at": "2026-07-03T00:00:00+00:00",
                    "updated_at": "2026-07-03T00:00:00+00:00",
                    "payload": {"action": "prompt_async", "prompt": "original"},
                },
            },
        },
    )

    first = opencode_queue._update_job(
        repo_root,
        job_id,
        {
            "status": "completed",
            "final_text": "DONE",
            "assistant": {"id": "assistant_1"},
            "messages": [{"role": "assistant", "finish": "stop", "text": "DONE"}],
        },
    )
    second = opencode_queue._update_job(repo_root, job_id, {"status": "completed", "final_text": "DONE again"})
    inbox = opencode_queue.list_notifications(repo_root)

    assert first["notification_id"] == second["notification_id"]
    assert inbox["count"] == 1
    assert inbox["unread_count"] == 1
    notification = inbox["notifications"][0]
    assert notification["job_id"] == job_id
    assert notification["status"] == "completed"
    assert notification["final_text"] == "DONE again"
    assert notification["next_action"] == "codex_review"


def test_opencode_queue_syncs_existing_terminal_notification_snapshot(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    job_id = "ocjob_sync"
    notification_id = "ocnote_existing"
    opencode_queue._save_state(
        repo_root,
        {
            "version": 1,
            "jobs": {
                job_id: {
                    "id": job_id,
                    "type": "prompt",
                    "title": "sync",
                    "status": "completed",
                    "created_at": "2026-07-03T00:00:00+00:00",
                    "updated_at": "2026-07-03T00:00:01+00:00",
                    "final_text": "fresh final",
                    "error": "fresh error",
                    "assistant": {"id": "assistant_fresh"},
                    "messages": [
                        {"role": "assistant", "finish": "stop", "text": "old"},
                        {"role": "assistant", "finish": "stop", "text": "fresh final"},
                    ],
                    "notification_id": notification_id,
                    "notification_status": "completed",
                    "notified_at": "2026-07-03T00:00:02+00:00",
                    "payload": {"action": "prompt_async", "prompt": "original"},
                },
            },
        },
    )
    opencode_queue._save_notifications(
        repo_root,
        {
            "version": 1,
            "notifications": {
                notification_id: {
                    "id": notification_id,
                    "kind": "opencode_job_terminal",
                    "job_id": job_id,
                    "job_type": "prompt",
                    "title": "sync",
                    "status": "completed",
                    "created_at": "2026-07-03T00:00:03+00:00",
                    "updated_at": "2026-07-03T00:00:03+00:00",
                    "job_updated_at": "2026-07-03T00:00:00+00:00",
                    "final_text": "stale final",
                    "error": "stale error",
                    "assistant_id": "assistant_stale",
                    "message_count": 1,
                    "read_at": "2026-07-03T00:00:04+00:00",
                    "acknowledged_by": "codex-test",
                    "next_action": "codex_review",
                },
            },
        },
    )

    inbox = opencode_queue.list_notifications(repo_root, unread_only=False)

    assert inbox["count"] == 1
    notification = inbox["notifications"][0]
    assert notification["id"] == notification_id
    assert notification["final_text"] == "fresh final"
    assert notification["error"] == "fresh error"
    assert notification["message_count"] == 2
    assert notification["assistant_id"] == "assistant_fresh"
    assert notification["read_at"] == "2026-07-03T00:00:04+00:00"
    assert notification["acknowledged_by"] == "codex-test"


def test_opencode_queue_refreshes_terminal_job_assistant_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = _make_repo(tmp_path)
    job_id = "ocjob_refresh_terminal"
    notification_id = "ocnote_refresh_terminal"
    opencode_queue._save_state(
        repo_root,
        {
            "version": 1,
            "jobs": {
                job_id: {
                    "id": job_id,
                    "type": "prompt",
                    "title": "refresh terminal",
                    "status": "completed",
                    "session_id": "ses_refresh",
                    "created_at": "2026-07-03T00:00:00+00:00",
                    "updated_at": "2026-07-03T00:00:01+00:00",
                    "final_text": "short",
                    "assistant": {"id": "assistant_old", "text": "short"},
                    "notification_id": notification_id,
                    "notification_status": "completed",
                    "notified_at": "2026-07-03T00:00:02+00:00",
                    "payload": {"action": "prompt_async", "prompt": "original"},
                },
            },
        },
    )
    opencode_queue._save_notifications(
        repo_root,
        {
            "version": 1,
            "notifications": {
                notification_id: {
                    "id": notification_id,
                    "kind": "opencode_job_terminal",
                    "job_id": job_id,
                    "job_type": "prompt",
                    "title": "refresh terminal",
                    "status": "completed",
                    "created_at": "2026-07-03T00:00:03+00:00",
                    "updated_at": "2026-07-03T00:00:03+00:00",
                    "job_updated_at": "2026-07-03T00:00:01+00:00",
                    "final_text": "short",
                    "assistant_id": "assistant_old",
                    "message_count": 1,
                    "read_at": "2026-07-03T00:00:04+00:00",
                    "acknowledged_by": "codex-test",
                    "next_action": "codex_review",
                },
            },
        },
    )
    monkeypatch.setattr(
        opencode_queue,
        "_refresh_messages",
        lambda *_args, **_kwargs: {
            "success": True,
            "messages": [
                {
                    "id": "assistant_fresh",
                    "role": "assistant",
                    "finish": "stop",
                    "text": "longer final answer",
                    "parts": [],
                },
            ],
        },
    )

    result = opencode_queue.get_job(repo_root, job_id, refresh=True)
    inbox = opencode_queue.list_notifications(repo_root, unread_only=False)

    assert result["job"]["status"] == "completed"
    assert result["job"]["final_text"] == "longer final answer"
    assert result["job"]["assistant"]["id"] == "assistant_fresh"
    notification = inbox["notifications"][0]
    assert notification["id"] == notification_id
    assert notification["final_text"] == "longer final answer"
    assert notification["assistant_id"] == "assistant_fresh"
    assert notification["read_at"] == "2026-07-03T00:00:04+00:00"
    assert notification["acknowledged_by"] == "codex-test"


def test_opencode_queue_backfill_reuses_legacy_notification_by_job_id(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    job_id = "ocjob_legacy_note"
    notification_id = "ocnote_legacy_existing"
    opencode_queue._save_state(
        repo_root,
        {
            "version": 1,
            "jobs": {
                job_id: {
                    "id": job_id,
                    "type": "prompt",
                    "title": "legacy note",
                    "status": "completed",
                    "created_at": "2026-07-03T00:00:00+00:00",
                    "updated_at": "2026-07-03T00:00:01+00:00",
                    "final_text": "fresh legacy final",
                    "assistant": {"id": "assistant_legacy"},
                    "messages": [{"role": "assistant", "finish": "stop", "text": "fresh legacy final"}],
                    "payload": {"action": "prompt_async", "prompt": "original"},
                },
            },
        },
    )
    opencode_queue._save_notifications(
        repo_root,
        {
            "version": 1,
            "notifications": {
                notification_id: {
                    "id": notification_id,
                    "kind": "opencode_job_terminal",
                    "job_id": job_id,
                    "job_type": "prompt",
                    "title": "legacy note",
                    "status": "completed",
                    "created_at": "2026-07-03T00:00:02+00:00",
                    "updated_at": "2026-07-03T00:00:02+00:00",
                    "job_updated_at": "2026-07-03T00:00:00+00:00",
                    "final_text": "stale legacy final",
                    "assistant_id": "assistant_stale",
                    "message_count": 1,
                    "read_at": "2026-07-03T00:00:03+00:00",
                    "acknowledged_by": "codex-test",
                    "next_action": "codex_review",
                },
            },
        },
    )

    inbox = opencode_queue.list_notifications(repo_root, unread_only=False)
    job = opencode_queue.get_job(repo_root, job_id, refresh=False)["job"]

    assert inbox["count"] == 1
    notification = inbox["notifications"][0]
    assert notification["id"] == notification_id
    assert notification["final_text"] == "fresh legacy final"
    assert notification["assistant_id"] == "assistant_legacy"
    assert notification["read_at"] == "2026-07-03T00:00:03+00:00"
    assert notification["acknowledged_by"] == "codex-test"
    assert job["notification_id"] == notification_id


def test_opencode_queue_notification_inbox_marks_read(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    job_id = "ocjob_mark_read"
    opencode_queue._save_state(
        repo_root,
        {
            "version": 1,
            "jobs": {
                job_id: {
                    "id": job_id,
                    "type": "prompt",
                    "title": "mark read",
                    "status": "completed",
                    "created_at": "2026-07-03T00:00:00+00:00",
                    "updated_at": "2026-07-03T00:00:00+00:00",
                    "final_text": "DONE",
                    "payload": {"action": "prompt_async", "prompt": "original"},
                },
            },
        },
    )

    unread = opencode_queue.list_notifications(repo_root)
    marked = opencode_queue.list_notifications(repo_root, mark_read=True, acknowledged_by="codex-test")
    after = opencode_queue.list_notifications(repo_root)

    assert unread["count"] == 1
    assert marked["unread_count_before_mark"] == 1
    assert marked["unread_count"] == 0
    assert marked["notifications"][0]["read_at"]
    assert marked["notifications"][0]["acknowledged_by"] == "codex-test"
    assert after["count"] == 0


def test_opencode_queue_redacts_password_on_disk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    captured_payloads: list[dict[str, object]] = []

    monkeypatch.setattr(opencode_queue, "_start_thread", lambda *_args, **_kwargs: None)

    result = opencode_queue.submit_job(
        repo_root,
        payload={"action": "prompt_async", "prompt": "secret"},
        title="secret",
        job_type="prompt",
        password="super-secret-token",
    )
    job = result["job"]
    state_text = (repo_root / "backend" / "logs" / "opencode-sdk-jobs.json").read_text(encoding="utf-8")

    assert result["success"] is True
    assert "super-secret-token" not in state_text
    assert job["has_password"] is True
    assert job["payload"]["has_password"] is True
    assert "password" not in job
    assert "password" not in job["payload"]

    def fake_run_sdk(_repo_root: Path, payload: dict[str, object], *, timeout_seconds: int = 120) -> dict[str, object]:
        captured_payloads.append(payload)
        return {"success": False, "error": "stop after capture"}

    monkeypatch.setattr(opencode_queue, "_run_sdk", fake_run_sdk)

    opencode_queue._worker(repo_root, job["id"])

    assert captured_payloads
    assert captured_payloads[0]["password"] == "super-secret-token"
