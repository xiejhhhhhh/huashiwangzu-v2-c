"""Runtime configuration and HTTP helpers for the release gate."""
from __future__ import annotations

import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    from dev_toolkit.config_loader import load_config
    from dev_toolkit.release_gate_support import ensure_envelope_success
except ModuleNotFoundError:
    from config_loader import load_config
    from release_gate_support import ensure_envelope_success

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULES_DIR = REPO_ROOT / "modules"
BACKEND_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"
CONFIG = load_config(REPO_ROOT)
BACKEND_BASE = str(CONFIG.get("backend_base_url") or "http://127.0.0.1:33000")
FRONTEND_BASE = str(CONFIG.get("frontend_base_url") or "http://127.0.0.1:5173")
SEMANTIC_COMPLETED_SCAN_LIMIT = 500

DB_DSN = CONFIG.get("db_dsn", "")
ACCOUNTS = CONFIG.get("accounts", {})
RELEASE_GATE_CONFIG = CONFIG.get("release_gate", {})

results: list[dict[str, Any]] = []
_token_cache: dict[str, tuple[str, float]] = {}
_TOKEN_MAX_AGE = 300  # 5 min — short enough to avoid stale-after-smoke expiry
runtime_context: dict[str, Any] = {}

def _project_python() -> str:
    return str(BACKEND_PYTHON if BACKEND_PYTHON.exists() else Path(sys.executable))

def _run_git(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""

def git_snapshot() -> dict[str, Any]:
    status_lines = [line for line in _run_git(["status", "--short"]).splitlines() if line.strip()]
    return {
        "sha": _run_git(["rev-parse", "HEAD"]),
        "short_sha": _run_git(["rev-parse", "--short", "HEAD"]),
        "branch": _run_git(["branch", "--show-current"]),
        "dirty": bool(status_lines),
        "dirty_count": len(status_lines),
        "dirty_files": status_lines[:80],
    }

def changed_module_keys(status_lines: list[str] | None = None) -> set[str]:
    lines = status_lines
    if lines is None:
        lines = [line for line in _run_git(["status", "--short"]).splitlines() if line.strip()]
    changed: set[str] = set()
    for line in lines:
        path = line[3:].strip()
        if path.startswith('"') and path.endswith('"'):
            continue
        match = re.match(r"modules/([^/]+)/", path)
        if match and not match.group(1).startswith("_"):
            changed.add(match.group(1))
    return changed

async def _url_status(base_url: str, path: str = "/") -> dict[str, Any]:
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5, trust_env=False) as client:
            resp = await client.get(path)
        return {
            "available": resp.status_code < 500,
            "status_code": resp.status_code,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        }
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        }

async def collect_runtime_context() -> None:
    runtime_context.clear()
    runtime_context.update({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend_base_url": BACKEND_BASE,
        "frontend_base_url": FRONTEND_BASE,
        "git": git_snapshot(),
        "services": {
            "backend": await _url_status(BACKEND_BASE, "/api/health"),
            "frontend": await _url_status(FRONTEND_BASE, "/"),
        },
    })

async def _ensure_token(*, force_refresh: bool = False) -> str:
    now = time.monotonic()
    if not force_refresh and "admin" in _token_cache:
        cached_token, cached_at = _token_cache["admin"]
        if now - cached_at < _TOKEN_MAX_AGE:
            return cached_token
    acct = ACCOUNTS["admin"]
    if not acct.get("username") or not acct.get("password"):
        raise RuntimeError(
            "dev_toolkit admin account is not configured; set dev_toolkit/config.local.json "
            "or DEV_TOOLKIT_ADMIN_USERNAME/DEV_TOOLKIT_ADMIN_PASSWORD"
        )
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=10, trust_env=False) as client:
        resp = await client.post("/api/login", json={
            "username": acct["username"],
            "password": acct["password"],
        })
        data = resp.json()
        token = data.get("data", {}).get("access_token") or data.get("access_token")
        if not token:
            raise RuntimeError(f"Login failed: {data}")
        _token_cache["admin"] = (token, now)
        return token

async def probe(method: str, path: str, body: dict | None = None) -> dict:
    token = await _ensure_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30, trust_env=False) as client:
        resp = await client.request(method, path, json=body, headers=headers)
        if resp.status_code == 401:
            token = await _ensure_token(force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            resp = await client.request(method, path, json=body, headers=headers)
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw": resp.text[:500]}
        if not 200 <= resp.status_code < 300:
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}",
                "status_code": resp.status_code,
                "data": payload,
            }
        return payload

async def fetch_task_queue_audit() -> dict[str, Any]:
    r = await probe("GET", "/api/tasks/worker/audit")
    ensure_envelope_success(r, "task queue audit")
    if not isinstance(r, dict):
        raise TypeError(f"unexpected response type: {type(r)}")
    d = r
    while isinstance(d, dict) and isinstance(d.get("data"), dict) and "summary" not in d:
        d = d["data"]
    if not isinstance(d, dict):
        raise TypeError(f"unexpected audit payload type: {type(d)}")
    return d

def audit_failed_count(audit: dict[str, Any]) -> int:
    summary = audit.get("summary", {})
    if not isinstance(summary, dict) or "failed" not in summary:
        raise ValueError("task queue audit missing summary.failed")
    value = summary.get("failed")
    return int(value or 0)

async def fetch_live_capabilities() -> list[dict[str, Any]]:
    payload = await probe("GET", "/api/modules/capabilities")
    ensure_envelope_success(payload, "module capabilities")
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        raise TypeError("module capabilities payload is not a list")
    return [item for item in data if isinstance(item, dict)]
