from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.services.model_watchdog.registry import ModelRecord

_RUNTIME_DIR = Path(__file__).resolve().parents[3] / "data" / "runtime" / "model_watchdog"
_LEASE_DIR = _RUNTIME_DIR / "leases"


def runtime_dir() -> Path:
    _LEASE_DIR.mkdir(parents=True, exist_ok=True)
    return _RUNTIME_DIR


def touch_model(record: ModelRecord) -> None:
    if record.model_type != "local":
        return
    runtime_dir()
    payload = {
        "model": record.name,
        "purpose": record.purpose,
        "port": record.port,
        "last_used_at": time.time(),
        "pid": os.getpid(),
    }
    _atomic_write_json(_last_used_path(record.name), payload)


def mark_model_starting(record: ModelRecord, message: str = "") -> None:
    if record.model_type != "local":
        return
    now = time.time()
    _atomic_write_json(
        _startup_path(record.name),
        {
            "model": record.name,
            "purpose": record.purpose,
            "port": record.port,
            "state": "starting",
            "message": message,
            "started_at": now,
            "updated_at": now,
            "last_progress_at": now,
            "progress_reason": "launch_requested",
            "pid": os.getpid(),
        },
    )


def mark_model_loading(record: ModelRecord, *, message: str = "", details: dict | None = None) -> None:
    if record.model_type != "local":
        return
    now = time.time()
    previous = _read_json(_startup_path(record.name))
    started_at = float(previous.get("started_at") or now)
    payload = {
        **previous,
        "model": record.name,
        "purpose": record.purpose,
        "port": record.port,
        "state": "loading",
        "message": message,
        "started_at": started_at,
        "updated_at": now,
        "last_progress_at": now,
        "progress_reason": (details or {}).get("progress_reason", "loading_progress"),
        "elapsed_seconds": max(0.0, now - started_at),
        "pid": os.getpid(),
    }
    if details:
        payload["details"] = details
    _atomic_write_json(_startup_path(record.name), payload)


def mark_model_healthy(record: ModelRecord, *, message: str = "", details: dict | None = None) -> None:
    if record.model_type != "local":
        return
    now = time.time()
    previous = _read_json(_startup_path(record.name))
    started_at = float(previous.get("started_at") or now)
    payload = {
        **previous,
        "model": record.name,
        "purpose": record.purpose,
        "port": record.port,
        "state": "healthy",
        "message": message,
        "started_at": started_at,
        "updated_at": now,
        "last_progress_at": now,
        "progress_reason": "health_check_passed",
        "elapsed_seconds": max(0.0, now - started_at),
        "pid": os.getpid(),
    }
    if details:
        payload["details"] = details
    _atomic_write_json(_startup_path(record.name), payload)


def mark_model_failed(record: ModelRecord, *, message: str, details: dict | None = None) -> None:
    if record.model_type != "local":
        return
    now = time.time()
    previous = _read_json(_startup_path(record.name))
    started_at = float(previous.get("started_at") or now)
    payload = {
        **previous,
        "model": record.name,
        "purpose": record.purpose,
        "port": record.port,
        "state": "failed",
        "message": message,
        "started_at": started_at,
        "updated_at": now,
        "elapsed_seconds": max(0.0, now - started_at),
        "pid": os.getpid(),
    }
    if details:
        payload["details"] = details
    _atomic_write_json(_startup_path(record.name), payload)


def model_startup_state(record: ModelRecord) -> dict:
    state = _read_json(_startup_path(record.name))
    if not state:
        return {
            "state": "unknown",
            "message": "",
            "started_at": None,
            "updated_at": None,
            "last_progress_at": None,
            "elapsed_seconds": None,
        }
    now = time.time()
    started_at = float(state.get("started_at") or 0)
    state["elapsed_seconds"] = max(0.0, now - started_at) if started_at else None
    return state


@contextmanager
def model_usage(record: ModelRecord) -> Iterator[None]:
    if record.model_type != "local":
        yield
        return
    touch_model(record)
    lease_path = _lease_path(record.name)
    _atomic_write_json(
        lease_path,
        {
            "model": record.name,
            "created_at": time.time(),
            "pid": os.getpid(),
        },
    )
    try:
        yield
    finally:
        touch_model(record)
        lease_path.unlink(missing_ok=True)


def model_runtime_state(record: ModelRecord, now: float | None = None) -> dict:
    now = now or time.time()
    last_used = _read_json(_last_used_path(record.name))
    active_leases = _active_leases(record.name, now)
    last_used_at = float(last_used.get("last_used_at") or 0)
    idle_seconds = max(0.0, now - last_used_at) if last_used_at else None
    return {
        "name": record.name,
        "purpose": record.purpose,
        "model_type": record.model_type,
        "port": record.port,
        "auto_unload": record.auto_unload,
        "idle_timeout_seconds": record.idle_timeout_seconds,
        "last_used_at": last_used_at or None,
        "idle_seconds": idle_seconds,
        "active_leases": len(active_leases),
        "leases": active_leases,
        "startup": model_startup_state(record),
    }


def should_reap_idle_model(
    record: ModelRecord,
    *,
    now: float | None = None,
) -> tuple[bool, str]:
    if record.model_type != "local":
        return False, "not_local"
    if not record.auto_unload:
        return False, "auto_unload_disabled"
    if record.idle_timeout_seconds <= 0:
        return False, "idle_timeout_disabled"
    state = model_runtime_state(record, now=now)
    if state["active_leases"] > 0:
        return False, "active_lease"
    idle_seconds = state["idle_seconds"]
    if idle_seconds is None:
        return False, "never_used"
    if idle_seconds < record.idle_timeout_seconds:
        return False, "not_idle"
    return True, "idle_timeout"


def _last_used_path(model_name: str) -> Path:
    return runtime_dir() / f"{model_name}.last_used.json"


def _startup_path(model_name: str) -> Path:
    return runtime_dir() / f"{model_name}.startup.json"


def _lease_path(model_name: str) -> Path:
    token = uuid.uuid4().hex
    return runtime_dir() / "leases" / f"{model_name}.{os.getpid()}.{token}.json"


def _active_leases(model_name: str, now: float) -> list[dict]:
    runtime_dir()
    leases: list[dict] = []
    for path in _LEASE_DIR.glob(f"{model_name}.*.json"):
        payload = _read_json(path)
        created_at = float(payload.get("created_at") or 0)
        pid = int(payload.get("pid") or 0)
        if pid and _pid_alive(pid):
            leases.append(payload)
            continue
        if created_at and now - created_at < 30:
            leases.append(payload)
            continue
        path.unlink(missing_ok=True)
    return leases


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
