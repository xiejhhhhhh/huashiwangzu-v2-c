"""Persistent background queue for OpenCode SDK tasks."""

from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

try:
    from dev_toolkit.opencode_common import (
        DEFAULT_HOST,
        DEFAULT_PORT,
        DEFAULT_SDK_PACKAGE,
        logs_dir,
        node_binary,
        now_iso,
        now_slug,
        npm_binary,
        opencode_env,
        safe_title,
        sdk_dir,
        sdk_script,
    )
except ModuleNotFoundError:
    from opencode_common import (
        DEFAULT_HOST,
        DEFAULT_PORT,
        DEFAULT_SDK_PACKAGE,
        logs_dir,
        node_binary,
        now_iso,
        now_slug,
        npm_binary,
        opencode_env,
        safe_title,
        sdk_dir,
        sdk_script,
    )

MAX_ACTIVE_JOBS = 20
MAX_NOTIFICATIONS = 500
NOTIFICATION_TEXT_LIMIT = 4000
TERMINAL_STATUSES = {"completed", "failed", "stalled", "timeout", "cancelled"}
CONTINUE_PROMPT = "继续执行刚才的任务。不要停在中途；如果已完成，请用简短清单汇报最终结果和验证状态。"

_LOCK = threading.RLock()
_THREADS: dict[str, threading.Thread] = {}
_JOB_SECRETS: dict[str, dict[str, str]] = {}
REDACTED_SECRET = "***redacted***"


def _jobs_path(repo_root: Path) -> Path:
    return logs_dir(repo_root) / "opencode-sdk-jobs.json"


def _notifications_path(repo_root: Path) -> Path:
    return logs_dir(repo_root) / "opencode-sdk-notifications.json"


def _job_monitor_lock_path(repo_root: Path, job_id: str) -> Path:
    return logs_dir(repo_root) / f"opencode-sdk-job-{job_id}.lock"


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _job_monitor_lock(repo_root: Path, job_id: str) -> Iterator[bool]:
    lock_path = _job_monitor_lock_path(repo_root, job_id)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _load_state(repo_root: Path) -> dict[str, Any]:
    path = _jobs_path(repo_root)
    if not path.exists():
        return {"version": 1, "jobs": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "jobs": {}}
    if not isinstance(data, dict):
        return {"version": 1, "jobs": {}}
    jobs = data.get("jobs")
    if not isinstance(jobs, dict):
        data["jobs"] = {}
    data.setdefault("version", 1)
    return data


def _load_notifications(repo_root: Path) -> dict[str, Any]:
    path = _notifications_path(repo_root)
    if not path.exists():
        return {"version": 1, "notifications": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "notifications": {}}
    if not isinstance(data, dict):
        return {"version": 1, "notifications": {}}
    notifications = data.get("notifications")
    if not isinstance(notifications, dict):
        data["notifications"] = {}
    data.setdefault("version", 1)
    return data


def _save_state(repo_root: Path, state: dict[str, Any]) -> None:
    path = _jobs_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _save_notifications(repo_root: Path, inbox: dict[str, Any]) -> None:
    path = _notifications_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    notifications = inbox.get("notifications")
    if isinstance(notifications, dict):
        ordered = sorted(
            notifications.values(),
            key=lambda item: str(item.get("created_at", "")) if isinstance(item, dict) else "",
            reverse=True,
        )[:MAX_NOTIFICATIONS]
        inbox["notifications"] = {
            str(item["id"]): item
            for item in ordered
            if isinstance(item, dict) and item.get("id")
        }
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(inbox, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _text_tail(value: Any, *, limit: int = NOTIFICATION_TEXT_LIMIT) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[-limit:]


def _notification_from_job(job_id: str, job: dict[str, Any], notification_id: str, created_at: str) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    assistant = job.get("assistant") if isinstance(job.get("assistant"), dict) else {}
    messages = job.get("messages") if isinstance(job.get("messages"), list) else []
    status = str(job.get("status") or "")
    final_text = _text_tail(job.get("final_text"))
    error = _text_tail(job.get("error"), limit=1200)
    return {
        "id": notification_id,
        "kind": "opencode_job_terminal",
        "job_id": job_id,
        "job_type": job.get("type"),
        "title": job.get("title") or job_id,
        "status": status,
        "session_id": job.get("session_id"),
        "agent": job.get("agent"),
        "letter_path": payload.get("letter_path"),
        "created_at": created_at,
        "updated_at": created_at,
        "job_updated_at": job.get("updated_at"),
        "final_text": final_text,
        "error": error,
        "assistant_id": assistant.get("id"),
        "message_count": len(messages),
        "read_at": None,
        "acknowledged_by": "",
        "next_action": "codex_review" if status == "completed" else "codex_triage",
    }


def _ensure_terminal_notification(repo_root: Path, state: dict[str, Any], job_id: str, job: dict[str, Any]) -> bool:
    status = str(job.get("status") or "")
    if status not in TERMINAL_STATUSES:
        return False
    if job.get("notify_on_terminal") is False:
        return False

    now = now_iso()
    notification_id = str(job.get("notification_id") or "")
    changed = False
    with _file_lock(_notifications_path(repo_root)):
        inbox = _load_notifications(repo_root)
        notifications = inbox.setdefault("notifications", {})
        if not notification_id:
            for candidate_id, candidate in notifications.items():
                if isinstance(candidate, dict) and candidate.get("job_id") == job_id:
                    notification_id = str(candidate.get("id") or candidate_id)
                    break
        if not notification_id:
            notification_id = f"ocnote_{uuid.uuid4().hex[:12]}"
        existing = notifications.get(notification_id)
        if isinstance(existing, dict):
            notification = _notification_from_job(
                job_id,
                job,
                notification_id,
                str(existing.get("created_at") or now),
            )
            notification["read_at"] = existing.get("read_at")
            notification["acknowledged_by"] = existing.get("acknowledged_by", "")
            if any(existing.get(key) != notification.get(key) for key in notification if key != "updated_at"):
                notification["updated_at"] = now
                notifications[notification_id] = notification
                changed = True
        else:
            notification = _notification_from_job(job_id, job, notification_id, now)
            notifications[notification_id] = notification
            changed = True
        if changed:
            _save_notifications(repo_root, inbox)

    if job.get("notification_id") != notification_id:
        job["notification_id"] = notification_id
        changed = True
    if job.get("notification_status") != status:
        job["notification_status"] = status
        changed = True
    if not job.get("notified_at"):
        job["notified_at"] = now
        changed = True
    if changed:
        state["jobs"][job_id] = job
    return changed


def _update_job(repo_root: Path, job_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        with _file_lock(_jobs_path(repo_root)):
            state = _load_state(repo_root)
            job = state["jobs"].get(job_id)
            if not isinstance(job, dict):
                raise KeyError(f"unknown opencode sdk job: {job_id}")
            job.update(updates)
            job["updated_at"] = now_iso()
            state["jobs"][job_id] = job
            _ensure_terminal_notification(repo_root, state, job_id, job)
            _save_state(repo_root, state)
            return job


def _active_count(state: dict[str, Any]) -> int:
    count = 0
    for job in state.get("jobs", {}).values():
        if isinstance(job, dict) and job.get("status") not in TERMINAL_STATUSES:
            count += 1
    return count


_node_binary = node_binary
_npm_binary = npm_binary


def _ensure_sdk_package(repo_root: Path) -> dict[str, Any]:
    sdk_package = repo_root / ".opencode" / "node_modules" / "@opencode-ai" / "sdk"
    if sdk_package.exists():
        return {"success": True, "installed": False, "path": str(sdk_package)}
    npm = _npm_binary()
    if not npm:
        return {"success": False, "error": "npm binary not found in PATH"}
    completed = subprocess.run(
        [npm, "install", DEFAULT_SDK_PACKAGE, "--prefix", ".opencode"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        timeout=120,
        env=opencode_env(),
        stdin=subprocess.DEVNULL,
        check=False,
    )
    return {
        "success": completed.returncode == 0 and sdk_package.exists(),
        "installed": completed.returncode == 0 and sdk_package.exists(),
        "path": str(sdk_package),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _run_sdk(repo_root: Path, payload: dict[str, Any], *, timeout_seconds: int = 120) -> dict[str, Any]:
    node = _node_binary()
    if not node:
        return {"success": False, "error": "node binary not found in PATH"}
    sdk_ready = _ensure_sdk_package(repo_root)
    if not sdk_ready.get("success"):
        return {"success": False, "error": "@opencode-ai/sdk is not installed", "sdk_install": sdk_ready}
    payload = {"directory": str(repo_root), **payload}
    command = [node, str(sdk_script(repo_root)), json.dumps(payload, ensure_ascii=False)]
    completed = subprocess.run(
        command,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        timeout=max(int(timeout_seconds), 1),
        env=opencode_env(),
        stdin=subprocess.DEVNULL,
        check=False,
    )
    log_root = sdk_dir(repo_root)
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / f"{now_slug()}-{safe_title(str(payload.get('action', 'sdk')))}.json"
    log_path.write_text((completed.stdout or "") + (completed.stderr or ""), encoding="utf-8")
    try:
        data = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        data = {
            "success": False,
            "error": "SDK helper returned non-JSON output",
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    data.setdefault("success", completed.returncode == 0)
    data["returncode"] = completed.returncode
    data["log_path"] = str(log_path)
    return data


def _message_signature(messages: list[dict[str, Any]]) -> str:
    serializable = [
        {
            "id": item.get("id"),
            "role": item.get("role"),
            "finish": item.get("finish"),
            "text": item.get("text"),
            "parts_count": len(item.get("parts") or []),
        }
        for item in messages
    ]
    raw = json.dumps(serializable, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _latest_assistant(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for message in reversed(messages):
        if message.get("role") == "assistant":
            return message
    return None


def _assistant_finished(message: dict[str, Any] | None) -> bool:
    if not message:
        return False
    if message.get("finish"):
        return True
    parts = message.get("parts") or []
    return any(isinstance(part, dict) and part.get("type") == "step-finish" for part in parts)


def _is_completed(messages: list[dict[str, Any]]) -> bool:
    latest = _latest_assistant(messages)
    return _assistant_finished(latest)


def _payload_value(job: dict[str, Any], key: str) -> Any:
    payload = job.get("payload")
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _job_password(job: dict[str, Any]) -> str | None:
    job_id = str(job.get("id") or "")
    secret = _JOB_SECRETS.get(job_id, {}).get("password")
    if secret:
        return secret
    for value in (job.get("password"), _payload_value(job, "password")):
        if value and value != REDACTED_SECRET:
            return str(value)
    return None


def _refresh_messages(repo_root: Path, job: dict[str, Any]) -> dict[str, Any]:
    session_id = job.get("session_id")
    if not session_id:
        return {"success": False, "error": "job has no session_id yet"}
    return _run_sdk(
        repo_root,
        {
            "action": "messages",
            "host": job.get("host", DEFAULT_HOST),
            "port": int(job.get("port", DEFAULT_PORT)),
            "session_id": session_id,
            "limit": int(job.get("message_limit", 50)),
            "username": job.get("username") or _payload_value(job, "username") or None,
            "password": _job_password(job),
        },
        timeout_seconds=60,
    )


def _send_continue(repo_root: Path, job: dict[str, Any]) -> dict[str, Any]:
    return _run_sdk(
        repo_root,
        {
            "action": "prompt_async",
            "host": job.get("host", DEFAULT_HOST),
            "port": int(job.get("port", DEFAULT_PORT)),
            "session_id": job["session_id"],
            "prompt": job.get("continue_prompt") or CONTINUE_PROMPT,
            "agent": job.get("agent") or None,
            "username": job.get("username") or _payload_value(job, "username") or None,
            "password": _job_password(job),
        },
        timeout_seconds=60,
    )


def _worker(repo_root: Path, job_id: str) -> None:
    try:
        with _job_monitor_lock(repo_root, job_id) as acquired:
            if not acquired:
                return
            job = _update_job(repo_root, job_id, {"status": "starting", "started_at": now_iso()})
            if job.get("session_id"):
                result = _refresh_messages(repo_root, job)
                if not result.get("success"):
                    _update_job(
                        repo_root,
                        job_id,
                        {"status": "failed", "error": result.get("error"), "last_result": result},
                    )
                    return
                messages = result.get("messages") or []
                signature = _message_signature(messages)
                updates: dict[str, Any] = {
                    "status": "running",
                    "messages": messages,
                    "last_result": result,
                    "last_signature": signature,
                    "last_progress_at": now_iso(),
                    "resumed_at": now_iso(),
                }
                if _is_completed(messages):
                    latest = _latest_assistant(messages) or {}
                    updates.update({
                        "status": "completed",
                        "completed_at": now_iso(),
                        "final_text": latest.get("text", ""),
                        "assistant": latest,
                    })
                job = _update_job(repo_root, job_id, updates)
                if job.get("status") in TERMINAL_STATUSES:
                    return
            else:
                payload = dict(job["payload"])
                password = _job_password(job)
                if password:
                    payload["password"] = password
                result = _run_sdk(repo_root, payload, timeout_seconds=120)
                if not result.get("success"):
                    _update_job(
                        repo_root,
                        job_id,
                        {"status": "failed", "error": result.get("error"), "last_result": result},
                    )
                    return
                session = result.get("session") or {}
                session_id = session.get("id")
                messages = result.get("messages") or []
                signature = _message_signature(messages)
                job = _update_job(
                    repo_root,
                    job_id,
                    {
                        "status": "running",
                        "session_id": session_id,
                        "session": session,
                        "messages": messages,
                        "last_result": result,
                        "last_signature": signature,
                        "last_progress_at": now_iso(),
                    },
                )
            deadline = time.time() + int(job.get("max_runtime_seconds", 7200))
            while time.time() < deadline:
                time.sleep(max(float(job.get("poll_seconds", 10)), 1.0))
                with _LOCK:
                    with _file_lock(_jobs_path(repo_root)):
                        current = _load_state(repo_root)["jobs"].get(job_id, {})
                if current.get("status") in TERMINAL_STATUSES:
                    return
                refreshed = _refresh_messages(repo_root, current)
                if not refreshed.get("success"):
                    _update_job(
                        repo_root,
                        job_id,
                        {"status": "failed", "error": refreshed.get("error"), "last_result": refreshed},
                    )
                    return
                messages = refreshed.get("messages") or []
                signature = _message_signature(messages)
                updates: dict[str, Any] = {"messages": messages, "last_result": refreshed}
                if signature != current.get("last_signature"):
                    updates["last_signature"] = signature
                    updates["last_progress_at"] = now_iso()
                if _is_completed(messages):
                    latest = _latest_assistant(messages) or {}
                    updates.update({
                        "status": "completed",
                        "completed_at": now_iso(),
                        "final_text": latest.get("text", ""),
                        "assistant": latest,
                    })
                    _update_job(repo_root, job_id, updates)
                    return
                last_progress = current.get("last_progress_at") or current.get("started_at") or current.get("created_at")
                last_progress_ts = (
                    datetime.fromisoformat(last_progress).timestamp()
                    if isinstance(last_progress, str)
                    else time.time()
                )
                stalled = time.time() - last_progress_ts >= int(current.get("stall_seconds", 120))
                if stalled:
                    continue_count = int(current.get("continue_count", 0))
                    max_continue = int(current.get("max_continue", 3))
                    if continue_count >= max_continue:
                        updates.update({"status": "stalled", "error": "job stalled after max_continue attempts"})
                        _update_job(repo_root, job_id, updates)
                        return
                    continued = _send_continue(repo_root, current)
                    updates.update({
                        "status": "running",
                        "continue_count": continue_count + 1,
                        "last_continue_at": now_iso(),
                        "last_continue_result": continued,
                        "last_progress_at": now_iso(),
                    })
                else:
                    updates["status"] = "running"
                _update_job(repo_root, job_id, updates)
            _update_job(repo_root, job_id, {"status": "timeout", "error": "job exceeded max_runtime_seconds"})
    except Exception as exc:  # pragma: no cover - defensive background guard
        try:
            _update_job(repo_root, job_id, {"status": "failed", "error": str(exc)})
        except Exception:
            pass
    finally:
        _THREADS.pop(job_id, None)


def _start_thread(repo_root: Path, job_id: str) -> None:
    if job_id in _THREADS and _THREADS[job_id].is_alive():
        return
    thread = threading.Thread(target=_worker, args=(repo_root, job_id), name=f"opencode-sdk-job-{job_id}", daemon=True)
    _THREADS[job_id] = thread
    thread.start()


def _thread_alive(job_id: str) -> bool:
    thread = _THREADS.get(job_id)
    return bool(thread and thread.is_alive())


def submit_job(
    repo_root: Path,
    *,
    payload: dict[str, Any],
    title: str,
    job_type: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    session_id: str = "",
    agent: str = "",
    username: str = "",
    password: str = "",
    poll_seconds: int = 10,
    stall_seconds: int = 120,
    max_continue: int = 3,
    max_runtime_seconds: int = 7200,
) -> dict[str, Any]:
    with _LOCK:
        with _file_lock(_jobs_path(repo_root)):
            state = _load_state(repo_root)
            if _active_count(state) >= MAX_ACTIVE_JOBS:
                return {
                    "success": False,
                    "error": f"too many active opencode jobs; limit={MAX_ACTIVE_JOBS}",
                    "active_count": _active_count(state),
                    "limit": MAX_ACTIVE_JOBS,
                }
            job_id = f"ocjob_{uuid.uuid4().hex[:12]}"
            payload = {
                **payload,
                "host": host,
                "port": port,
                "session_id": session_id or None,
                "agent": agent or None,
                "username": username or None,
                "has_password": bool(password),
            }
            if password:
                _JOB_SECRETS[job_id] = {"password": password}
            job = {
                "id": job_id,
                "type": job_type,
                "title": title or job_id,
                "status": "queued",
                "host": host,
                "port": port,
                "session_id": session_id or None,
                "agent": agent or None,
                "username": username or None,
                "has_password": bool(password),
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "payload": payload,
                "poll_seconds": max(int(poll_seconds), 1),
                "stall_seconds": max(int(stall_seconds), 10),
                "max_continue": max(int(max_continue), 0),
                "continue_count": 0,
                "max_runtime_seconds": max(int(max_runtime_seconds), 60),
                "message_limit": 50,
            }
            state["jobs"][job_id] = job
            _save_state(repo_root, state)
    _start_thread(repo_root, job_id)
    time.sleep(0.2)
    return {"success": True, "job": get_job(repo_root, job_id)["job"], "active_limit": MAX_ACTIVE_JOBS}


def get_job(repo_root: Path, job_id: str, *, refresh: bool = True) -> dict[str, Any]:
    with _LOCK:
        with _file_lock(_jobs_path(repo_root)):
            state = _load_state(repo_root)
            job = state["jobs"].get(job_id)
    if not isinstance(job, dict):
        return {"success": False, "error": f"unknown opencode sdk job: {job_id}"}
    if refresh and job.get("session_id"):
        refreshed = _refresh_messages(repo_root, job)
        if refreshed.get("success"):
            messages = refreshed.get("messages") or []
            signature = _message_signature(messages)
            updates = {"messages": messages, "last_result": refreshed, "last_signature": signature}
            if signature != job.get("last_signature"):
                updates["last_progress_at"] = now_iso()
            if _is_completed(messages):
                latest = _latest_assistant(messages) or {}
                updates.update({"final_text": latest.get("text", ""), "assistant": latest})
                if job.get("status") not in TERMINAL_STATUSES:
                    updates.update({"status": "completed", "completed_at": now_iso()})
            job = _update_job(repo_root, job_id, updates)
    if job.get("status") not in TERMINAL_STATUSES and not _thread_alive(job_id):
        _start_thread(repo_root, job_id)
    return {"success": True, "job": job, "thread_alive": _thread_alive(job_id)}


def list_jobs(repo_root: Path, *, status: str = "", limit: int = 50) -> dict[str, Any]:
    with _LOCK:
        with _file_lock(_jobs_path(repo_root)):
            state = _load_state(repo_root)
            all_jobs = list(state.get("jobs", {}).values())
    jobs = all_jobs
    if status:
        jobs = [job for job in jobs if isinstance(job, dict) and job.get("status") == status]
    jobs = sorted(jobs, key=lambda item: item.get("created_at", ""), reverse=True)[: max(int(limit), 1)]
    active = [job for job in all_jobs if isinstance(job, dict) and job.get("status") not in TERMINAL_STATUSES]
    return {"success": True, "jobs": jobs, "count": len(jobs), "active_count": len(active), "active_limit": MAX_ACTIVE_JOBS}


def _backfill_terminal_notifications(repo_root: Path) -> None:
    with _LOCK:
        with _file_lock(_jobs_path(repo_root)):
            state = _load_state(repo_root)
            changed = False
            jobs = state.get("jobs", {})
            if not isinstance(jobs, dict):
                return
            for job_id, job in jobs.items():
                if not isinstance(job, dict):
                    continue
                changed = _ensure_terminal_notification(repo_root, state, str(job_id), job) or changed
            if changed:
                _save_state(repo_root, state)


def list_notifications(
    repo_root: Path,
    *,
    status: str = "",
    unread_only: bool = True,
    limit: int = 20,
    mark_read: bool = False,
    acknowledged_by: str = "codex",
) -> dict[str, Any]:
    _backfill_terminal_notifications(repo_root)
    with _LOCK:
        with _file_lock(_notifications_path(repo_root)):
            inbox = _load_notifications(repo_root)
            notifications = [
                item
                for item in inbox.get("notifications", {}).values()
                if isinstance(item, dict)
            ]
            unread_total = sum(1 for item in notifications if not item.get("read_at"))
            if status:
                notifications = [item for item in notifications if item.get("status") == status]
            if unread_only:
                notifications = [item for item in notifications if not item.get("read_at")]
            notifications.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
            selected = notifications[: max(int(limit), 1)]
            if mark_read and selected:
                now = now_iso()
                inbox_notifications = inbox.setdefault("notifications", {})
                for item in selected:
                    notification_id = str(item.get("id") or "")
                    stored = inbox_notifications.get(notification_id)
                    if not isinstance(stored, dict):
                        continue
                    stored["read_at"] = stored.get("read_at") or now
                    stored["acknowledged_by"] = acknowledged_by or "codex"
                    stored["updated_at"] = now
                    item.update(stored)
                _save_notifications(repo_root, inbox)
            unread_after = sum(
                1
                for item in inbox.get("notifications", {}).values()
                if isinstance(item, dict) and not item.get("read_at")
            )
    return {
        "success": True,
        "inbox_path": str(_notifications_path(repo_root)),
        "notifications": selected,
        "count": len(selected),
        "unread_count": unread_after if mark_read else unread_total,
        "unread_count_before_mark": unread_total,
    }


def continue_job(repo_root: Path, job_id: str, *, prompt: str = CONTINUE_PROMPT) -> dict[str, Any]:
    current = get_job(repo_root, job_id, refresh=False)
    if not current.get("success"):
        return current
    job = current["job"]
    if not job.get("session_id"):
        return {"success": False, "error": "job has no session_id yet", "job": job}
    result = _run_sdk(
        repo_root,
        {
            "action": "prompt_async",
            "host": job.get("host", DEFAULT_HOST),
            "port": int(job.get("port", DEFAULT_PORT)),
            "session_id": job["session_id"],
            "prompt": prompt,
            "agent": job.get("agent") or None,
            "username": job.get("username") or _payload_value(job, "username") or None,
            "password": _job_password(job),
        },
        timeout_seconds=60,
    )
    updated = _update_job(
        repo_root,
        job_id,
        {
            "status": "running",
            "last_manual_continue_at": now_iso(),
            "last_continue_result": result,
            "last_progress_at": now_iso(),
            "continue_count": int(job.get("continue_count", 0)) + 1,
        },
    )
    if updated.get("status") not in TERMINAL_STATUSES:
        _start_thread(repo_root, job_id)
    return {"success": result.get("success", False), "job": updated, "continue_result": result}
