"""Background job wrappers for long-running project toolkit commands."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dev_toolkit.code_tools import (
        normalize_pytest_targets,
        pytest_targets_for_command,
        resolve_repo_path,
        split_path_list,
    )
    from dev_toolkit.process_tools import popen_process_group, terminate_popen_tree
except ModuleNotFoundError:
    from code_tools import normalize_pytest_targets, pytest_targets_for_command, resolve_repo_path, split_path_list
    from process_tools import popen_process_group, terminate_popen_tree


TOOL_NAMES = {"tool_job_submit", "tool_job_status", "tool_job_notifications"}
SUPPORTED_TOOLS = {"release_gate", "run_test", "smoke_all", "module_sandbox_matrix", "lint"}
_LOCK = threading.RLock()
_OUTPUT_TAIL_LIMIT = 20000
_STALE_AFTER_SECONDS = 900


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_python(repo_root: Path) -> str:
    backend_python = repo_root / "backend" / ".venv" / "bin" / "python"
    return str(backend_python if backend_python.exists() else Path(sys.executable))


def _ruff_cli(repo_root: Path) -> str:
    return str(repo_root / "backend" / ".venv" / "bin" / "ruff")


def _state_path(repo_root: Path) -> Path:
    return repo_root / "backend" / "logs" / "tool-jobs.json"


def _notifications_path(repo_root: Path) -> Path:
    return repo_root / "backend" / "logs" / "tool-job-notifications.json"


def _job_log_dir(repo_root: Path) -> Path:
    return repo_root / "backend" / "logs" / "tool-jobs"


def _lock_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".lock")


@contextmanager
def _file_lock(path: Path):
    lock_path = _lock_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _load_jobs(repo_root: Path) -> dict[str, Any]:
    data = _read_json(_state_path(repo_root), {"jobs": {}})
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
        return {"jobs": {}}
    return data


def _save_jobs(repo_root: Path, data: dict[str, Any]) -> None:
    _write_json_atomic(_state_path(repo_root), data)


def _update_job(repo_root: Path, job_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    state_path = _state_path(repo_root)
    with _file_lock(state_path):
        data = _load_jobs(repo_root)
        jobs = data.setdefault("jobs", {})
        job = dict(jobs.get(job_id) or {})
        job.update(updates)
        job["updated_at"] = _utc_now()
        jobs[job_id] = job
        _save_jobs(repo_root, data)
        return job


def _append_notification(repo_root: Path, job_id: str, level: str, message: str) -> None:
    notification_path = _notifications_path(repo_root)
    with _file_lock(notification_path):
        data = _read_json(notification_path, {"next_id": 1, "notifications": []})
        if not isinstance(data, dict):
            data = {"next_id": 1, "notifications": []}
        notifications = data.setdefault("notifications", [])
        next_id = int(data.get("next_id") or 1)
        notifications.append({
            "id": next_id,
            "job_id": job_id,
            "level": level,
            "message": message,
            "created_at": _utc_now(),
        })
        data["next_id"] = next_id + 1
        data["notifications"] = notifications[-200:]
        _write_json_atomic(notification_path, data)


def _tail_text(text: str, limit: int = _OUTPUT_TAIL_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _tail_file(path: Path, limit: int = _OUTPUT_TAIL_LIMIT) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    return _tail_text(text, limit)


def _extract_prefixed_json(output: str, prefix: str) -> dict[str, Any] | None:
    for line in reversed(output.splitlines()):
        text = line.strip()
        if not text.startswith(prefix):
            continue
        try:
            data = json.loads(text[len(prefix):].strip())
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    return None


def _build_command(repo_root: Path, tool_name: str, arguments: dict[str, Any]) -> tuple[list[str], Path, dict[str, str], int]:
    env = os.environ.copy()
    timeout_seconds = int(arguments.get("timeout") or arguments.get("timeout_seconds") or 0)
    if tool_name == "release_gate":
        mode = str(arguments.get("mode") or "preflight")
        if mode not in {"preflight", "full"}:
            raise ValueError("release_gate mode must be 'preflight' or 'full'")
        cmd = [_project_python(repo_root), str(repo_root / "dev_toolkit" / "release_gate.py")]
        if mode == "preflight":
            cmd.append("--preflight")
        if bool(arguments.get("skip_ui", False)):
            cmd.append("--skip-ui")
            env["RELEASE_GATE_SKIP_UI"] = "1"
        if arguments.get("sandbox_jobs") is not None:
            cmd.extend(["--sandbox-jobs", str(max(1, int(arguments["sandbox_jobs"])))])
        if arguments.get("sandbox_frontend_jobs") is not None:
            cmd.extend(["--sandbox-frontend-jobs", str(max(1, int(arguments["sandbox_frontend_jobs"])))])
        return cmd, repo_root, env, timeout_seconds or (120 if mode == "preflight" else 600)

    if tool_name == "smoke_all":
        if bool(arguments.get("skip_ui", False)):
            env["SMOKE_SKIP_UI"] = "1"
        return [_project_python(repo_root), str(repo_root / "dev_toolkit" / "smoke.py")], repo_root, env, timeout_seconds or 360

    if tool_name == "module_sandbox_matrix":
        cmd = [_project_python(repo_root), str(repo_root / "dev_toolkit" / "module_sandbox_matrix.py")]
        if bool(arguments.get("check", False)):
            cmd.append("--check")
        cmd.append("--json")
        return cmd, repo_root, env, timeout_seconds or 300

    if tool_name == "run_test":
        target = str(arguments.get("target") or "").strip()
        if not target:
            raise ValueError("run_test requires target")
        normalized_targets = normalize_pytest_targets(repo_root, target)
        backend_dir = repo_root / "backend"
        command_targets = pytest_targets_for_command(backend_dir, normalized_targets)
        cmd = [str(backend_dir / ".venv" / "bin" / "pytest"), *command_targets]
        cwd = backend_dir
        if any(Path(item.partition("::")[0]).is_absolute() for item in command_targets):
            cwd = repo_root
            pythonpath = str(repo_root)
            if env.get("PYTHONPATH"):
                pythonpath = f"{pythonpath}:{env['PYTHONPATH']}"
            env["PYTHONPATH"] = pythonpath
        return cmd, cwd, env, timeout_seconds or int(arguments.get("pytest_timeout") or 120)

    if tool_name == "lint":
        path = str(arguments.get("path") or "")
        paths = split_path_list(path)
        if not paths:
            raise ValueError("lint requires path")
        cmd = [_ruff_cli(repo_root), "check"]
        if bool(arguments.get("diff", False)):
            cmd.append("--diff")
        for item in paths:
            resolved = resolve_repo_path(repo_root, item)
            if not resolved.exists():
                raise ValueError(f"file does not exist: {item}")
            cmd.append(str(resolved))
        return cmd, repo_root, env, timeout_seconds or 120

    raise ValueError(f"unsupported job tool: {tool_name}")


def _parse_result(tool_name: str, returncode: int, output: str) -> dict[str, Any]:
    if tool_name == "release_gate":
        summary = _extract_prefixed_json(output, "RELEASE_GATE_JSON:")
        verdict = summary.get("verdict") if summary else ("PASS" if returncode == 0 else "FAIL")
        release_safe_verdicts = {"PASS", "PASS_WITH_DEBT"}
        if summary and "clean_pass" in summary:
            clean_pass = bool(summary.get("clean_pass"))
        else:
            clean_pass = verdict == "PASS"
        if summary and "release_safe" in summary:
            release_safe = bool(summary.get("release_safe"))
        else:
            release_safe = returncode == 0 and verdict in release_safe_verdicts
        return {
            "success": returncode == 0 and clean_pass,
            "clean_pass": clean_pass,
            "release_safe": release_safe,
            "has_debt": bool(summary.get("has_debt")) if summary and "has_debt" in summary else verdict == "PASS_WITH_DEBT",
            "verdict": verdict,
            "summary": summary,
        }
    if tool_name == "smoke_all":
        summary = _extract_prefixed_json(output, "SMOKE_JSON:")
        verdict = summary.get("verdict") if summary else ("PASS" if returncode == 0 else "FAIL")
        return {"success": returncode == 0 and verdict == "PASS", "verdict": verdict, "summary": summary}
    if tool_name == "module_sandbox_matrix":
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            data = None
        return {"success": returncode in {0, 1}, "data": data}
    return {"success": returncode == 0}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _status_flags(job: dict[str, Any]) -> dict[str, Any]:
    status = str(job.get("status") or "")
    returncode = job.get("returncode")
    parsed = job.get("parsed_result")
    command_success = returncode == 0
    clean_success = bool(parsed.get("success")) if isinstance(parsed, dict) else status == "completed"
    release_safe = parsed.get("release_safe") if isinstance(parsed, dict) and "release_safe" in parsed else None
    return {
        "job_success": status == "completed",
        "command_success": command_success,
        "clean_success": clean_success,
        "release_safe": release_safe,
        "success": clean_success,
    }


def _stale_orphan_flags(job: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    status = str(job.get("status") or "")
    if status not in {"queued", "running"}:
        return {"stale": False, "orphaned": False, "stale_reason": ""}

    now = now or datetime.now(timezone.utc)
    updated_at = _parse_timestamp(job.get("updated_at"))
    timeout_seconds = int(job.get("timeout_seconds") or 0)
    stale_after = max(_STALE_AFTER_SECONDS, timeout_seconds * 2)
    pid = job.get("pid")
    if isinstance(pid, int) and not _pid_exists(pid):
        return {"stale": True, "orphaned": True, "stale_reason": f"pid {pid} no longer exists"}
    if updated_at is not None:
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_seconds = (now - updated_at).total_seconds()
        if age_seconds > stale_after:
            return {
                "stale": True,
                "orphaned": False,
                "stale_reason": f"no job state update for {int(age_seconds)}s",
            }
    return {"stale": False, "orphaned": False, "stale_reason": ""}


def _mark_stale_notified(repo_root: Path, job_id: str, flags: dict[str, Any]) -> dict[str, Any]:
    state_path = _state_path(repo_root)
    should_notify = False
    with _file_lock(state_path):
        data = _load_jobs(repo_root)
        jobs = data.setdefault("jobs", {})
        job = dict(jobs.get(job_id) or {})
        if job and not job.get("stale_notified_at"):
            job["stale_notified_at"] = _utc_now()
            job["stale"] = flags["stale"]
            job["orphaned"] = flags["orphaned"]
            job["stale_reason"] = flags["stale_reason"]
            jobs[job_id] = job
            _save_jobs(repo_root, data)
            should_notify = True
    if should_notify:
        reason = str(flags.get("stale_reason") or "stale job")
        _append_notification(repo_root, job_id, "warning", f"job stale/orphaned: {reason}")
    return job if isinstance(job, dict) else {}


def _run_job(repo_root: Path, job_id: str) -> None:
    job = _update_job(repo_root, job_id, {"status": "running", "started_at": _utc_now()})
    tool_name = str(job.get("tool_name") or "")
    command = list(job.get("command") or [])
    cwd = Path(str(job.get("cwd") or repo_root))
    env = dict(os.environ.copy())
    env.update(job.get("env_overrides") or {})
    timeout_seconds = int(job.get("timeout_seconds") or 120)
    log_path = Path(str(job.get("log_path")))
    output = ""
    proc = None
    started = time.monotonic()
    try:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"$ {' '.join(command)}\n\n")
            log.flush()
            proc = popen_process_group(command, cwd=cwd, env=env, stdout=log, stderr=log, text=True)
            _update_job(repo_root, job_id, {"pid": proc.pid})
            try:
                proc.wait(timeout=timeout_seconds)
            except (TimeoutError, subprocess.TimeoutExpired):
                terminate_popen_tree(proc)
                output = _tail_file(log_path)
                _update_job(
                    repo_root,
                    job_id,
                    {
                        "status": "timeout",
                        "completed_at": _utc_now(),
                        "duration_seconds": round(time.monotonic() - started, 3),
                        "returncode": proc.returncode,
                        "timeout": True,
                        "output_tail": output,
                    },
                )
                _append_notification(repo_root, job_id, "error", f"{tool_name} timed out after {timeout_seconds}s")
                return
        output = _tail_file(log_path)
        parsed = _parse_result(tool_name, int(proc.returncode or 0), output)
        status = "completed" if int(proc.returncode or 0) == 0 else "failed"
        _update_job(
            repo_root,
            job_id,
            {
                "status": status,
                "completed_at": _utc_now(),
                "duration_seconds": round(time.monotonic() - started, 3),
                "returncode": proc.returncode,
                "parsed_result": parsed,
                "output_tail": output,
            },
        )
        level = "info" if status == "completed" else "error"
        if status == "completed":
            verdict = parsed.get("verdict") if isinstance(parsed, dict) else None
            if verdict == "PASS_WITH_DEBT":
                _append_notification(repo_root, job_id, level, f"{tool_name} completed with debt")
            else:
                _append_notification(repo_root, job_id, level, f"{tool_name} completed")
        else:
            _append_notification(repo_root, job_id, level, f"{tool_name} failed")
    except Exception as exc:
        if proc is not None:
            terminate_popen_tree(proc)
        output = _tail_file(log_path)
        _update_job(
            repo_root,
            job_id,
            {
                "status": "failed",
                "completed_at": _utc_now(),
                "duration_seconds": round(time.monotonic() - started, 3),
                "error": str(exc),
                "output_tail": output,
            },
        )
        _append_notification(repo_root, job_id, "error", f"{tool_name} failed: {exc}")


def submit_job(repo_root: Path, tool_name: str, arguments: dict[str, Any], title: str = "") -> dict[str, Any]:
    if tool_name not in SUPPORTED_TOOLS:
        raise ValueError(f"tool_name must be one of {sorted(SUPPORTED_TOOLS)}")
    command, cwd, env, timeout_seconds = _build_command(repo_root, tool_name, arguments)
    job_id = f"job_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    log_dir = _job_log_dir(repo_root)
    log_dir.mkdir(parents=True, exist_ok=True)
    env_overrides = {
        key: value for key, value in env.items()
        if os.environ.get(key) != value and key in {"PYTHONPATH", "SMOKE_SKIP_UI", "RELEASE_GATE_SKIP_UI"}
    }
    job = {
        "job_id": job_id,
        "tool_name": tool_name,
        "title": title or tool_name,
        "status": "queued",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "timeout_seconds": timeout_seconds,
        "command": command,
        "cwd": str(cwd),
        "env_overrides": env_overrides,
        "arguments": arguments,
        "log_path": str(log_dir / f"{job_id}.log"),
    }
    with _file_lock(_state_path(repo_root)):
        data = _load_jobs(repo_root)
        data.setdefault("jobs", {})[job_id] = job
        _save_jobs(repo_root, data)
    thread = threading.Thread(target=_run_job, args=(repo_root, job_id), name=f"tool-job-{job_id}", daemon=True)
    thread.start()
    _append_notification(repo_root, job_id, "info", f"{tool_name} queued")
    return {
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "tool_name": tool_name,
        "title": job["title"],
        "timeout_seconds": timeout_seconds,
        "log_path": job["log_path"],
    }


def job_status(repo_root: Path, job_id: str, refresh: bool = True) -> dict[str, Any]:
    with _file_lock(_state_path(repo_root)):
        data = _load_jobs(repo_root)
        job = data.get("jobs", {}).get(job_id)
    if not isinstance(job, dict):
        return {"success": False, "error": f"unknown job_id: {job_id}"}
    payload = dict(job)
    if refresh:
        payload["output_tail"] = _tail_file(Path(str(job.get("log_path"))))
        stale_flags = _stale_orphan_flags(payload)
        if stale_flags["stale"] and not payload.get("stale_notified_at"):
            payload = _mark_stale_notified(repo_root, job_id, stale_flags) or payload
            payload["output_tail"] = _tail_file(Path(str(payload.get("log_path"))))
        else:
            payload.update(stale_flags)
    else:
        payload.update({
            "stale": bool(payload.get("stale", False)),
            "orphaned": bool(payload.get("orphaned", False)),
            "stale_reason": str(payload.get("stale_reason") or ""),
        })
    payload.update(_status_flags(payload))
    return payload


def notifications(repo_root: Path, since_notification_id: int = 0, limit: int = 50) -> dict[str, Any]:
    notification_path = _notifications_path(repo_root)
    with _file_lock(notification_path):
        data = _read_json(notification_path, {"next_id": 1, "notifications": []})
    items = data.get("notifications", []) if isinstance(data, dict) else []
    selected = [item for item in items if int(item.get("id") or 0) > since_notification_id]
    return {
        "success": True,
        "notifications": selected[-max(1, min(limit, 200)):],
        "next_id": data.get("next_id", 1) if isinstance(data, dict) else 1,
    }


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="tool_job_submit",
            description="把长时间 MCP 工具提交为后台 job 并立即返回. 支持 release_gate/run_test/smoke_all/module_sandbox_matrix/lint.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "enum": sorted(SUPPORTED_TOOLS)},
                    "arguments": {"type": "object", "default": {}},
                    "title": {"type": "string", "default": ""},
                    "timeout_seconds": {"type": "number", "description": "覆盖 job 超时时间(秒)"},
                },
                "required": ["tool_name", "arguments"],
            },
        ),
        Tool(
            name="tool_job_status",
            description="读取后台 job 状态、解析结果和日志尾部.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "refresh": {"type": "boolean", "default": True},
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="tool_job_notifications",
            description="读取后台 job 完成/失败通知.",
            inputSchema={
                "type": "object",
                "properties": {
                    "since_notification_id": {"type": "number", "default": 0},
                    "limit": {"type": "number", "default": 50},
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    if name == "tool_job_submit":
        submit_args = dict(arguments.get("arguments") or {})
        if arguments.get("timeout_seconds") is not None:
            submit_args["timeout_seconds"] = int(arguments["timeout_seconds"])
        result = submit_job(repo_root, str(arguments["tool_name"]), submit_args, str(arguments.get("title") or ""))
        return json.dumps(result, ensure_ascii=False, indent=2)
    if name == "tool_job_status":
        result = job_status(repo_root, str(arguments["job_id"]), bool(arguments.get("refresh", True)))
        return json.dumps(result, ensure_ascii=False, indent=2)
    if name == "tool_job_notifications":
        result = notifications(
            repo_root,
            since_notification_id=int(arguments.get("since_notification_id") or 0),
            limit=int(arguments.get("limit") or 50),
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    raise ValueError(f"unknown tool job tool: {name}")
