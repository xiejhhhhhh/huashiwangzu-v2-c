"""File-based cross-worker lock service.

Uses JSON file persistence (locks.json) to ensure locks are shared across
all uvicorn workers. The read-modify-write cycle is protected by an OS file
lock; atomic writes via temp file + rename prevent torn files.

Lock model:
  - acquire_lock(path, agent_id, ttl=600) -> {success: bool, error: str}
  - check_lock(path) -> {locked: bool, owner: str, remaining_ttl: float}
  - release_lock(path) -> {success: bool}
  - list_locks() -> {locks: [{path, agent_id, expires_at, remaining_ttl}]}
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger("v2.codemap").getChild("file_lock")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LOCK_FILE = DATA_DIR / "locks.json"
OS_LOCK_FILE = DATA_DIR / "locks.json.lock"
_LOCK_FILE_LOCK = threading.Lock()


class LockStoreError(RuntimeError):
    """Raised when the persisted lock store cannot be trusted."""


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read_locks() -> dict:
    if not LOCK_FILE.exists():
        return {}
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise LockStoreError("lock file is corrupt; refusing to ignore active locks") from exc
    except OSError as exc:
        raise LockStoreError(f"failed to read lock file: {exc}") from exc
    if not isinstance(data, dict):
        raise LockStoreError("lock file must contain a JSON object")
    for path, lock in data.items():
        if (
            not isinstance(path, str)
            or not isinstance(lock, dict)
            or not isinstance(lock.get("agent_id"), str)
            or not isinstance(lock.get("expires_at"), (int, float))
        ):
            raise LockStoreError("lock file contains malformed lock entries")
    return data


def _write_locks(locks: dict) -> bool:
    """Atomically write locks dict to file (temp + rename)."""
    try:
        _ensure_data_dir()
        fd, tmp_path = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(locks, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(LOCK_FILE))
            try:
                dir_fd = os.open(str(DATA_DIR), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                logger.debug("Could not fsync lock directory", exc_info=True)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return True
    except OSError as exc:
        logger.error("Failed to write lock file: %s", exc)
        return False


def _normalize_path(path: str) -> str:
    clean = path.strip().replace("\\", "/")
    if not clean:
        raise ValueError("path is required")
    raw = Path(clean)
    if raw.is_absolute():
        try:
            clean = str(raw.resolve().relative_to(PROJECT_ROOT.resolve()))
        except ValueError as exc:
            raise ValueError("path must be inside repository root") from exc
        raw = Path(clean)
    parts: list[str] = []
    for part in raw.parts:
        if part in ("", ".", os.sep):
            continue
        if part == "..":
            if not parts:
                raise ValueError("path cannot escape repository root")
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise ValueError("path is required")
    return "/".join(parts)


def _expire_locks(locks: dict) -> None:
    """Remove expired locks in-place."""
    now = time.time()
    expired = [p for p, lk in locks.items() if lk.get("expires_at", 0) <= now]
    for p in expired:
        del locks[p]


def _with_locked_locks(mutator) -> dict:
    """Run *mutator* while holding thread and process locks."""
    _ensure_data_dir()
    with _LOCK_FILE_LOCK:
        with open(OS_LOCK_FILE, "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                return mutator(_read_locks())
            except LockStoreError as exc:
                logger.error("Lock store unavailable: %s", exc)
                return {"success": False, "error": str(exc)}
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def acquire_lock(path: str, agent_id: str, ttl: int = 600) -> dict:
    """Acquire a lock on *path* for *agent_id* with *ttl* seconds TTL."""
    try:
        norm_path = _normalize_path(path)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    agent_id = agent_id.strip()
    if not agent_id:
        return {"success": False, "error": "agent_id is required"}
    if ttl <= 0:
        return {"success": False, "error": "ttl must be positive"}

    def _mutate(locks: dict) -> dict:
        expires_at = time.time() + ttl
        _expire_locks(locks)
        existing = locks.get(norm_path)
        if existing and existing.get("agent_id") != agent_id:
            remaining = existing["expires_at"] - time.time()
            return {
                "success": False,
                "error": f"Already locked by agent '{existing['agent_id']}' "
                         f"(remaining TTL: {max(0, round(remaining, 1))}s)",
            }
        locks[norm_path] = {"agent_id": agent_id, "expires_at": expires_at}
        if not _write_locks(locks):
            return {"success": False, "error": "Failed to persist lock"}
        return {"success": True, "path": norm_path, "agent_id": agent_id, "ttl": ttl}

    return _with_locked_locks(_mutate)


def check_lock(path: str) -> dict:
    """Check if *path* is locked."""
    try:
        norm_path = _normalize_path(path)
    except ValueError as exc:
        return {"success": False, "error": str(exc), "locked": False, "owner": None, "remaining_ttl": 0.0}

    def _mutate(locks: dict) -> dict:
        _expire_locks(locks)
        if not _write_locks(locks):
            return {"success": False, "error": "Failed to persist expired lock cleanup"}
        lock = locks.get(norm_path)
        if lock and lock.get("expires_at", 0) > time.time():
            remaining = lock["expires_at"] - time.time()
            return {"success": True, "locked": True, "owner": lock.get("agent_id", ""),
                    "remaining_ttl": round(remaining, 1)}
        return {"success": True, "locked": False, "owner": None, "remaining_ttl": 0.0}

    return _with_locked_locks(_mutate)


def release_lock(path: str) -> dict:
    """Release the lock on *path*."""
    try:
        norm_path = _normalize_path(path)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    def _mutate(locks: dict) -> dict:
        if norm_path not in locks:
            return {"success": False, "error": "No lock found for path"}
        del locks[norm_path]
        if not _write_locks(locks):
            return {"success": False, "error": "Failed to persist lock release"}
        return {"success": True, "path": norm_path}

    return _with_locked_locks(_mutate)


def list_locks() -> dict:
    """List all active locks."""
    def _mutate(locks: dict) -> dict:
        _expire_locks(locks)
        if not _write_locks(locks):
            return {"success": False, "error": "Failed to persist expired lock cleanup", "locks": [], "count": 0}
        now = time.time()
        result = [
            {"path": p, "agent_id": lk["agent_id"],
             "expires_at": lk["expires_at"],
             "remaining_ttl": max(0, round(lk["expires_at"] - now, 1))}
            for p, lk in locks.items()
            if lk.get("expires_at", 0) > now
        ]
        return {"success": True, "locks": result, "count": len(result)}

    return _with_locked_locks(_mutate)
