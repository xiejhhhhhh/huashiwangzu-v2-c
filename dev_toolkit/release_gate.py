"""Release gate — pre-publish validation matrix.

Aggregates:
  1. /api/health
  2. /api/system/status
  3. smoke_all(default includes UI; --skip-ui marks backend coverage debt)
  4. Task queue audit (gate-run additions vs historical debt)
  5. Module sandbox matrix summary

Output levels:
  - PASS       everything green
  - BLOCKER    must fix before release (gate-run failures, health non-ok, worker down)
  - DEBT       known historical issues, tracked not blocking
  - SKIPPED_WITH_REASON  intentionally skipped (e.g. no sandbox test)

Usage:
    cd <repo> && backend/.venv/bin/python dev_toolkit/release_gate.py [--skip-ui] [--preflight]
"""
import argparse
import asyncio
import json
import os
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
    from dev_toolkit.process_tools import create_subprocess_exec_group, terminate_process_tree
    from dev_toolkit.sql_guard import readonly_psql_env
except ModuleNotFoundError:
    from config_loader import load_config
    from process_tools import create_subprocess_exec_group, terminate_process_tree
    from sql_guard import readonly_psql_env

REPO_ROOT = Path(__file__).resolve().parent.parent
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


def add_result(check: str, level: str, detail: str, data: dict[str, Any] | None = None) -> None:
    item = {"check": check, "level": level, "detail": detail}
    if data is not None:
        item["data"] = data
    results.append(item)
    icon = {"PASS": "✅", "BLOCKER": "🔴", "DEBT": "🟡", "SKIPPED_WITH_REASON": "⏭️"}.get(level, "❓")
    print(f"  {icon} [{level:>20}] {check}: {detail[:200]}")


def _non_empty_error(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _legacy_code_failure(value: Any) -> bool:
    if value in (None, "", 0, "0"):
        return False
    if isinstance(value, bool):
        return value is not False
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        try:
            return float(value.strip()) != 0
        except ValueError:
            return False
    return False


def semantic_failure_reason(payload: Any, *, _depth: int = 0) -> str | None:
    if _depth > 8:
        return None
    if isinstance(payload, str):
        text = payload.strip()
        if not text or text[0] not in "{[":
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    if payload.get("success") is False:
        return _non_empty_error(payload.get("error")) or "success=false"
    error = _non_empty_error(payload.get("error"))
    if error:
        return error
    status = payload.get("status")
    if isinstance(status, str) and status.lower() in {"failed", "error"}:
        return f"status={status}"
    if "code" in payload and _legacy_code_failure(payload.get("code")):
        return (
            _non_empty_error(payload.get("message"))
            or _non_empty_error(payload.get("msg"))
            or f"code={payload.get('code')}"
        )
    for key in ("data", "result"):
        inner = payload.get(key)
        if isinstance(inner, (dict, str)):
            reason = semantic_failure_reason(inner, _depth=_depth + 1)
            if reason:
                return reason
    return None


def ensure_envelope_success(payload: Any, label: str) -> None:
    reason = semantic_failure_reason(payload)
    if reason:
        raise ValueError(f"{label} semantic failure: {reason}")


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


def _task_result_is_semantic_failure(result: dict[str, Any] | None) -> tuple[bool, str | None]:
    reason = semantic_failure_reason(result)
    return reason is not None, reason


def _decode_task_result(raw_result: Any) -> dict[str, Any] | None:
    if isinstance(raw_result, dict):
        return raw_result
    if not isinstance(raw_result, str) or not raw_result.strip():
        return None
    try:
        decoded = json.loads(raw_result)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _find_semantic_failed_completed_tasks_local(limit: int) -> tuple[int, list[dict[str, Any]]]:
    if not DB_DSN:
        raise RuntimeError("dev_toolkit config missing db_dsn")
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError("psycopg2 is required in the active interpreter") from exc

    samples: list[dict[str, Any]] = []
    with psycopg2.connect(DB_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            select id, task_type, module, result, completed_at
            from framework_system_task_queues
            where status = 'completed' and result is not null
            order by completed_at desc nulls last, id desc
            limit %s
            """,
            (limit,),
        )
        rows = cur.fetchall()

    count = 0
    for task_id, task_type, module, raw_result, completed_at in rows:
        result = _decode_task_result(raw_result)
        failed, reason = _task_result_is_semantic_failure(result)
        if not failed:
            continue
        count += 1
        if len(samples) < 5:
            samples.append({
                "id": task_id,
                "task_type": task_type,
                "module": module,
                "reason": reason,
                "completed_at": completed_at.isoformat() if completed_at else None,
            })
    return count, samples


def _find_semantic_failed_completed_tasks_via_backend_python(limit: int) -> tuple[int, list[dict[str, Any]]]:
    if not BACKEND_PYTHON.exists():
        raise RuntimeError("backend venv python not found for semantic task-result inspection")
    if Path(sys.executable).resolve() == BACKEND_PYTHON.resolve():
        raise RuntimeError("psycopg2 is unavailable in backend venv")

    proc = subprocess.run(
        [str(BACKEND_PYTHON), str(Path(__file__).resolve()), "--semantic-scan-json", str(limit)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[:500]
        raise RuntimeError(f"backend-python semantic scan failed: {detail}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"backend-python semantic scan returned invalid JSON: {proc.stdout[:500]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("backend-python semantic scan returned non-object JSON")
    return int(payload.get("count") or 0), list(payload.get("samples") or [])


def find_semantic_failed_completed_tasks(limit: int = SEMANTIC_COMPLETED_SCAN_LIMIT) -> tuple[int, list[dict[str, Any]]]:
    """Find completed queue rows whose result contract still says failed/error."""
    try:
        return _find_semantic_failed_completed_tasks_local(limit)
    except RuntimeError as exc:
        if "psycopg2 is required" not in str(exc):
            raise
        return _find_semantic_failed_completed_tasks_via_backend_python(limit)


def _run_psql_json(sql: str) -> dict[str, Any]:
    if not DB_DSN:
        raise RuntimeError("dev_toolkit config missing db_dsn")
    proc = subprocess.run(
        ["psql", DB_DSN, "-t", "-A", "-q", "-c", sql],
        cwd=str(REPO_ROOT),
        env=readonly_psql_env(os.environ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"psql failed: {detail[:500]}")
    output = proc.stdout.strip()
    return json.loads(output) if output else {}


def _asset_marker_predicate(alias: str, column: str) -> str:
    markers = (
        "smoke-",
        "e2e-",
        "recycle-",
        "pytest-",
        "test-upload-",
        "test-file-",
        "test-pollution-",
        "lifecycle-source-",
        "permanent-source-",
    )
    field = f"lower(coalesce({alias}.{column}, ''))"
    return "(" + " or ".join(f"{field} like '%{marker}%'" for marker in markers) + ")"


def audit_knowledge_lifecycle_debt() -> dict[str, Any]:
    return _run_psql_json(
        """
select json_build_object(
  'active_docs', count(*),
  'source_available', count(*) filter (where fi.id is not null and fi.deleted=false),
  'source_recycled', count(*) filter (where fi.id is not null and fi.deleted=true),
  'source_missing', count(*) filter (where fi.id is null),
  'source_unavailable', count(*) filter (where fi.id is null or fi.deleted=true),
  'sample_document_ids', coalesce((
    select json_agg(id) from (
      select d2.id
      from kb_documents d2
      left join framework_file_items fi2 on fi2.id = d2.file_id
      where d2.deleted=false and (fi2.id is null or fi2.deleted=true)
      order by d2.id desc
      limit 10
    ) s
  ), '[]'::json)
)
from kb_documents d
left join framework_file_items fi on fi.id = d.file_id
where d.deleted=false;
"""
    )


def audit_content_package_lifecycle_debt() -> dict[str, Any]:
    return _run_psql_json(
        """
select json_build_object(
  'active_packages', count(*),
  'source_available', count(*) filter (where p.source_file_id is not null and fi.id is not null and fi.deleted=false),
  'source_recycled', count(*) filter (where p.source_file_id is not null and fi.id is not null and fi.deleted=true),
  'source_missing', count(*) filter (where p.source_file_id is not null and fi.id is null),
  'without_source_file_id', count(*) filter (where p.source_file_id is null),
  'source_unavailable', count(*) filter (where p.source_file_id is not null and (fi.id is null or fi.deleted=true)),
  'archived_by_lifecycle', count(*) filter (
    where p.status='archived'
      and p.parse_error in (
        'source_file_deleted',
        'source_file_missing',
        'source_file_permanently_deleted',
        'archived_by_test_data_cleanup'
      )
  ),
  'unarchived_source_unavailable', count(*) filter (
    where p.source_file_id is not null
      and (fi.id is null or fi.deleted=true)
      and not (
        p.status='archived'
        and p.parse_error in (
          'source_file_deleted',
          'source_file_missing',
          'source_file_permanently_deleted',
          'archived_by_test_data_cleanup'
        )
      )
  ),
  'missing_current_version_total', count(*) filter (where p.current_version_id is null),
  'missing_current_version', count(*) filter (
    where p.current_version_id is null
      and p.source_file_id is not null
      and p.status in ('parsed', 'degraded', 'partial')
  ),
  'sample_package_ids', coalesce((
    select json_agg(id) from (
      select p2.id
      from framework_content_packages p2
      left join framework_file_items fi2 on fi2.id = p2.source_file_id
      where p2.deleted=false and p2.source_file_id is not null and (fi2.id is null or fi2.deleted=true)
      order by p2.id desc
      limit 10
    ) s
  ), '[]'::json)
)
from framework_content_packages p
left join framework_file_items fi on fi.id = p.source_file_id
where p.deleted=false;
"""
    )


def audit_test_data_pollution() -> dict[str, Any]:
    file_marker = _asset_marker_predicate("f", "name")
    storage_marker = _asset_marker_predicate("f", "storage_path")
    doc_marker = _asset_marker_predicate("d", "filename")
    return _run_psql_json(
        f"""
with marker_files as (
  select f.id, f.deleted
  from framework_file_items f
  where {file_marker} or {storage_marker}
),
marker_docs as (
  select d.id, d.deleted
  from kb_documents d
  left join marker_files mf on mf.id = d.file_id
  where mf.id is not null or {doc_marker}
),
marker_packages as (
  select p.id, p.deleted
  from framework_content_packages p
  join marker_files mf on mf.id = p.source_file_id
)
select json_build_object(
  'active_test_files', (select count(*) from marker_files where deleted=false),
  'recycled_test_files', (select count(*) from marker_files where deleted=true),
  'knowledge_documents_from_test_files', (select count(*) from marker_docs where deleted=false),
  'content_packages_from_test_files', (select count(*) from marker_packages where deleted=false),
  'uploads_test_artifacts', (select count(*) from marker_files),
  'markers', json_build_array(
    'smoke-', 'e2e-', 'recycle-', 'pytest-', 'test-upload-', 'test-file-',
    'test-pollution-', 'lifecycle-source-', 'permanent-source-'
  )
)::text;
"""
    )


def classify_semantic_failed_completed(
    current_count: int,
    baseline_count: int | None,
    samples: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    samples = samples or []
    if baseline_count is None:
        return "BLOCKER", "missing pre-smoke semantic-failed-completed baseline"
    delta = max(0, int(current_count or 0) - int(baseline_count or 0))
    if delta > 0:
        names = ", ".join(f"#{s.get('id')}:{s.get('task_type')}" for s in samples[:3])
        detail = f"semantic-failed completed tasks increased: {baseline_count} -> {current_count} (+{delta})"
        if names:
            detail += f"; samples={names}"
        return "BLOCKER", detail
    if current_count > 0:
        return "DEBT", f"{current_count} historical completed task(s) contain failed/error result contracts"
    return "PASS", "no semantic-failed completed task results in recent completed scan"


def parse_prefixed_json(output: str, prefix: str) -> dict[str, Any] | None:
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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"__error__": str(exc), "__path__": str(path.relative_to(REPO_ROOT))}
    return data if isinstance(data, dict) else {"__error__": "manifest is not an object"}


def load_module_manifests() -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    if not MODULES_DIR.exists():
        return manifests
    for path in sorted(MODULES_DIR.glob("*/manifest.json")):
        if path.parent.name.startswith("_"):
            continue
        data = _read_json(path)
        key = str(data.get("key") or path.parent.name)
        manifests.append({
            "key": key,
            "path": path,
            "module_dir": path.parent,
            "data": data,
        })
    return manifests


def _public_action_names(actions: Any) -> set[str]:
    if isinstance(actions, dict):
        return {str(action) for action in actions if action}
    if isinstance(actions, list):
        return {
            str(item.get("action"))
            for item in actions
            if isinstance(item, dict) and item.get("action")
        }
    return set()


def scan_manifest_public_actions(manifests: list[dict[str, Any]] | None = None) -> set[tuple[str, str]]:
    entries: set[tuple[str, str]] = set()
    for item in manifests or load_module_manifests():
        data = item.get("data") or {}
        if data.get("__error__"):
            continue
        module_key = str(data.get("key") or item.get("key"))
        for action in _public_action_names(data.get("public_actions")):
            entries.add((module_key, action))
    return entries


def scan_source_registered_capabilities() -> set[tuple[str, str]]:
    """Best-effort static scan for register_capability declarations.

    The live registry is authoritative. This scan catches common literal and
    tuple-list registrations so drift is visible without importing modules.
    """
    manifests = load_module_manifests()
    module_keys = {str(item["key"]) for item in manifests}
    known_modules = module_keys | {"content", "_self"}
    entries: set[tuple[str, str]] = set()
    paths = [p for p in MODULES_DIR.glob("*/backend/**/*.py") if not p.parent.name.startswith("_")]
    paths.extend((REPO_ROOT / "backend" / "app" / "routers").glob("*.py"))
    direct = re.compile(
        r"register_capability\(\s*['\"]([A-Za-z0-9_-]+)['\"]\s*,\s*['\"]([A-Za-z0-9_-]+)['\"]"
    )
    tuple_decl = re.compile(
        r"\(\s*['\"]([A-Za-z0-9_-]+)['\"]\s*,\s*['\"]([A-Za-z0-9_-]+)['\"]\s*,"
    )
    cap_handler_tuple = re.compile(r"\(\s*['\"]([A-Za-z0-9_-]+)['\"]\s*,\s*_cap_")

    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "register_capability" not in text:
            continue
        entries.update(direct.findall(text))
        for module_key, action in tuple_decl.findall(text):
            if module_key in known_modules:
                entries.add((module_key, action))
        if "register_capability(" in text and '"content"' in text:
            for action in cap_handler_tuple.findall(text):
                entries.add(("content", action))
    return entries


async def fetch_live_capabilities() -> list[dict[str, Any]]:
    payload = await probe("GET", "/api/modules/capabilities")
    ensure_envelope_success(payload, "module capabilities")
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        raise TypeError("module capabilities payload is not a list")
    return [item for item in data if isinstance(item, dict)]


def classify_capability_drift(
    live_capabilities: list[dict[str, Any]],
    *,
    manifests: list[dict[str, Any]] | None = None,
    source_registered: set[tuple[str, str]] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    manifests = manifests or load_module_manifests()
    manifest_modules = {str(item["key"]) for item in manifests}
    manifest_actions = scan_manifest_public_actions(manifests)
    source_actions = source_registered if source_registered is not None else scan_source_registered_capabilities()
    live_actions = {
        (str(item.get("module")), str(item.get("action")))
        for item in live_capabilities
        if item.get("module") and item.get("action")
    }
    live_public = {item for item in live_actions if item[0] in manifest_modules}
    source_public = {item for item in source_actions if item[0] in manifest_modules}

    missing_live = sorted(manifest_actions - live_public)
    undeclared_live = sorted(live_public - manifest_actions)
    source_not_live = sorted(source_public - live_public)
    manifest_not_source = sorted(manifest_actions - source_public)

    data = {
        "manifest_count": len(manifest_actions),
        "live_public_count": len(live_public),
        "source_public_count": len(source_public),
        "missing_live": missing_live[:20],
        "undeclared_live": undeclared_live[:20],
        "source_not_live": source_not_live[:20],
        "manifest_not_source": manifest_not_source[:20],
        "missing_live_count": len(missing_live),
        "undeclared_live_count": len(undeclared_live),
        "source_not_live_count": len(source_not_live),
        "manifest_not_source_count": len(manifest_not_source),
    }
    if missing_live or undeclared_live or source_not_live:
        level = "BLOCKER"
    elif manifest_not_source:
        level = "DEBT"
    else:
        level = "PASS"
    detail = (
        f"manifest={len(manifest_actions)}, live={len(live_public)}, source={len(source_public)}, "
        f"missing_live={len(missing_live)}, undeclared_live={len(undeclared_live)}, "
        f"source_not_live={len(source_not_live)}, manifest_not_source={len(manifest_not_source)}"
    )
    return level, detail, data


def _readme_acceptance_ok(module_dir: Path) -> bool:
    readme = module_dir / "README.md"
    if not readme.exists():
        return False
    try:
        text = readme.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    has_acceptance = any(marker in text for marker in ("验收", "验证", "acceptance"))
    has_command = any(
        marker in text
        for marker in ("sandbox", "test_module.py", "npm run build", "backend/.venv/bin/python", "pytest")
    )
    return has_acceptance and has_command


def classify_readme_acceptance_matrix(
    manifests: list[dict[str, Any]] | None = None,
    changed_modules: set[str] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    manifests = manifests or load_module_manifests()
    changed_modules = changed_modules if changed_modules is not None else changed_module_keys()
    missing = sorted(
        str(item["key"])
        for item in manifests
        if not _readme_acceptance_ok(Path(item["module_dir"]))
    )
    changed_missing = sorted(key for key in missing if key in changed_modules)
    data = {
        "module_count": len(manifests),
        "missing_count": len(missing),
        "changed_missing_count": len(changed_missing),
        "missing_modules": missing[:30],
        "changed_missing_modules": changed_missing[:30],
    }
    if changed_missing:
        level = "BLOCKER"
    elif missing:
        level = "DEBT"
    else:
        level = "PASS"
    detail = (
        f"modules={len(manifests)}, missing={len(missing)}, "
        f"changed_missing={len(changed_missing)}"
    )
    return level, detail, data


def classify_component_key_contracts(
    manifests: list[dict[str, Any]] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    manifests = manifests or load_module_manifests()
    issues: list[dict[str, str]] = []
    for item in manifests:
        data = item.get("data") or {}
        module_key = str(item["key"])
        if data.get("__error__"):
            issues.append({"module": module_key, "issue": str(data["__error__"])})
            continue
        component_key = str(data.get("component_key") or "").strip()
        window_type = str(data.get("window_type") or "normal")
        module_dir = Path(item["module_dir"])
        if window_type == "background-service":
            if component_key:
                issues.append({
                    "module": module_key,
                    "issue": "background-service must use empty component_key",
                })
            continue
        if not component_key:
            issues.append({"module": module_key, "issue": "normal app has empty component_key"})
            continue
        if not (module_dir / "frontend" / component_key).exists():
            issues.append({"module": module_key, "issue": f"component_key target missing: {component_key}"})
    data = {
        "module_count": len(manifests),
        "issue_count": len(issues),
        "issues": issues[:30],
    }
    level = "BLOCKER" if issues else "PASS"
    detail = f"modules={len(manifests)}, issues={len(issues)}"
    return level, detail, data


def classify_sandbox_matrix(entries: list[dict[str, Any]], elapsed: float) -> tuple[str, str]:
    total = len(entries)
    passed = sum(1 for e in entries if e.get("check") == "pass")
    failed = sum(1 for e in entries if e.get("check") == "fail")
    skipped = sum(1 for e in entries if e.get("check") == "skip")
    chunk_warning_modules = [
        str(e.get("module"))
        for e in entries
        if e.get("chunk_warnings")
        or any(result.get("chunk_warnings") for result in e.get("command_results", []) if isinstance(result, dict))
    ]

    if failed > 0:
        fail_names = [e["module"] for e in entries if e.get("check") == "fail"]
        return (
            "BLOCKER",
            f"{total} modules, {passed} pass, {failed} fail ({', '.join(fail_names)}), {skipped} skip ({elapsed:.0f}s)",
        )
    if chunk_warning_modules:
        return (
            "DEBT",
            f"{total} modules, {passed} pass, {skipped} skip, chunk warnings in {len(chunk_warning_modules)} "
            f"({', '.join(chunk_warning_modules[:5])}) ({elapsed:.0f}s)",
        )
    if skipped > 0:
        return "DEBT", f"{total} modules, {passed} pass, {skipped} skip ({elapsed:.0f}s) — skipped is tracked debt"
    return "PASS", f"{total} modules, {passed} pass, 0 skip ({elapsed:.0f}s)"


async def check_health() -> None:
    try:
        r = await probe("GET", "/api/health")
        ensure_envelope_success(r, "health")
        d = r.get("data", r)
        status = d.get("status", "unknown")
        if status == "ok":
            add_result("Health check", "PASS", f"status={status}, db={d.get('database')}")
        else:
            add_result("Health check", "BLOCKER", f"status={status}, db={d.get('database')}")
        runtime_context["health"] = d
    except Exception as e:
        add_result("Health check", "BLOCKER", str(e))


async def check_system_status() -> None:
    try:
        r = await probe("GET", "/api/system/status")
        ensure_envelope_success(r, "system status")
        d = r.get("data", r)
        backend_ok = d.get("backend", {}).get("status") is True
        db_ok = d.get("database", {}).get("status") is True
        worker_ok = d.get("worker", {}).get("status") is True
        if backend_ok and db_ok and worker_ok:
            add_result("System status", "PASS", "backend/db/worker all ok")
        else:
            failing = [k for k in ("backend", "database", "worker") if not d.get(k, {}).get("status")]
            add_result("System status", "BLOCKER", f"failing: {', '.join(failing)}")
        runtime_context["system_status"] = d
    except Exception as e:
        add_result("System status", "BLOCKER", str(e))


async def check_smoke(skip_ui: bool) -> None:
    proc: asyncio.subprocess.Process | None = None
    try:
        started = time.monotonic()
        env_override = {"SMOKE_SKIP_UI": "1"} if skip_ui else {}
        env = {**os.environ.copy(), **env_override}
        proc = await create_subprocess_exec_group(
            _project_python(),
            str(REPO_ROOT / "dev_toolkit" / "smoke.py"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=REPO_ROOT,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=360)
        elapsed = time.monotonic() - started
        output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
        passed = proc.returncode == 0
        smoke_summary = parse_prefixed_json(output, "SMOKE_JSON:")

        if smoke_summary:
            runtime_context["smoke"] = {
                "summary": smoke_summary,
                "returncode": proc.returncode,
                "duration_seconds": round(elapsed, 3),
                "skip_ui": skip_ui,
            }
            verdict = smoke_summary.get("verdict")
            counts = smoke_summary.get("counts", {})
            failed = int(counts.get("failed", 0) or 0) if isinstance(counts, dict) else 0
            skipped = int(counts.get("skipped", 0) or 0) if isinstance(counts, dict) else 0
            skipped_scenarios = smoke_summary.get("skipped_scenarios", [])
            if not passed or verdict == "FAIL":
                add_result("Smoke test (backends)", "BLOCKER",
                           f"{elapsed:.0f}s, exit={proc.returncode}, failed={failed}")
            elif verdict == "PASS_WITH_DEBT":
                names = ", ".join(str(item) for item in skipped_scenarios[:3])
                add_result("Smoke test (backends)", "DEBT",
                           f"{elapsed:.0f}s, passed with debt; skipped={skipped} ({names})")
            elif verdict == "PASS":
                add_result("Smoke test (backends)", "PASS",
                           f"{elapsed:.0f}s, clean pass")
            else:
                add_result("Smoke test (backends)", "BLOCKER",
                           f"{elapsed:.0f}s, unknown smoke verdict={verdict!r}")
            check_ui_smoke_summary(smoke_summary, skip_ui=skip_ui)
            check_model_fallback_summary(smoke_summary)
            return

        if passed:
            add_result("Smoke test (backends)", "BLOCKER",
                       f"{elapsed:.0f}s, missing SMOKE_JSON machine summary")
        else:
            # Extract failure count from output
            fail_lines = [line for line in output.splitlines() if "R]" in line or "❌" in line or "[R]" in line]
            add_result("Smoke test (backends)", "BLOCKER",
                       f"{elapsed:.0f}s, exit={proc.returncode}, failures: {len(fail_lines)}")
    except asyncio.TimeoutError:
        if proc is not None:
            await terminate_process_tree(proc)
        add_result("Smoke test (backends)", "BLOCKER", "timeout (>360s)")
    except asyncio.CancelledError:
        if proc is not None:
            await terminate_process_tree(proc)
        raise
    except Exception as e:
        add_result("Smoke test (backends)", "BLOCKER", str(e))


def check_ui_coverage(skip_ui: bool) -> None:
    if skip_ui:
        runtime_context["ui_coverage"] = {
            "status": "DEBT",
            "included": False,
            "reason": "--skip-ui used",
        }
        add_result(
            "UI coverage",
            "DEBT",
            "--skip-ui used; backend preflight only, not a clean release gate",
        )
        return
    runtime_context["ui_coverage"] = {
        "status": "PENDING",
        "included": True,
        "reason": "waiting for smoke Playwright summary",
    }
    add_result("UI coverage", "PASS", "UI smoke coverage included")


def check_ui_smoke_summary(smoke_summary: dict[str, Any], *, skip_ui: bool) -> None:
    if skip_ui:
        return
    ui_summary = smoke_summary.get("ui")
    if not isinstance(ui_summary, dict):
        runtime_context["ui_coverage"] = {
            "status": "BLOCKER",
            "included": True,
            "reason": "smoke summary missing ui field",
        }
        add_result("UI Playwright summary", "BLOCKER", "smoke summary missing UI machine summary")
        return

    failed = int(ui_summary.get("failed") or 0)
    passed = int(ui_summary.get("passed") or 0)
    skipped = int(ui_summary.get("skipped") or 0)
    status = str(ui_summary.get("status") or "")
    failed_tests = ui_summary.get("failed_tests") if isinstance(ui_summary.get("failed_tests"), list) else []
    artifacts = ui_summary.get("artifact_paths") if isinstance(ui_summary.get("artifact_paths"), list) else []
    runtime_context["ui_coverage"] = {
        "status": "PASS" if status == "pass" and failed == 0 else ("DEBT" if status == "unavailable" else "BLOCKER"),
        "included": True,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "failed_tests": failed_tests[:10],
        "artifact_paths": artifacts[:20],
        "duration_seconds": ui_summary.get("duration_seconds"),
    }
    if status == "pass" and failed == 0:
        add_result("UI Playwright summary", "PASS", f"passed={passed}, skipped={skipped}, artifacts={len(artifacts)}")
    elif status == "unavailable":
        add_result("UI Playwright summary", "DEBT", str(ui_summary.get("reason") or "UI environment unavailable"))
    else:
        names = ", ".join(str(item.get("title", "?")) for item in failed_tests[:3] if isinstance(item, dict))
        add_result(
            "UI Playwright summary",
            "BLOCKER",
            f"failed={failed}, passed={passed}, artifacts={len(artifacts)}" + (f"; tests={names}" if names else ""),
        )


def check_model_fallback_summary(smoke_summary: dict[str, Any]) -> None:
    model_summary = smoke_summary.get("model_fallback")
    if not isinstance(model_summary, dict):
        runtime_context["model_fallback"] = {
            "status": "DEBT",
            "reason": "smoke summary missing model_fallback field",
        }
        add_result("Model fallback", "DEBT", "smoke summary missing model fallback summary")
        return

    status = str(model_summary.get("status") or "PASS")
    observations = model_summary.get("observations") if isinstance(model_summary.get("observations"), list) else []
    runtime_context["model_fallback"] = {
        "status": status,
        "fallback_used_count": int(model_summary.get("fallback_used_count") or 0),
        "blocker_count": int(model_summary.get("blocker_count") or 0),
        "observations": observations[:10],
    }
    if status == "BLOCKER":
        add_result("Model fallback", "BLOCKER", f"{runtime_context['model_fallback']['blocker_count']} model fallback blocker(s)")
    elif status == "DEBT":
        sample = observations[0] if observations and isinstance(observations[0], dict) else {}
        detail = str(sample.get("summary") or f"{model_summary.get('fallback_used_count', 0)} fallback debt observation(s)")
        add_result("Model fallback", "DEBT", detail)
    else:
        add_result("Model fallback", "PASS", "no blocking model fallback debt observed")


async def check_task_queue_audit(
    baseline_failed: int | None,
    baseline_semantic_failed_completed: int | None = None,
) -> None:
    try:
        d = await fetch_task_queue_audit()
        summary = d.get("summary", {})
        classification = d.get("classification", {})
        stalest = d.get("stalest_pending")
        runtime_context["task_debt_summary"] = {
            "summary": summary,
            "classification": classification,
            "recent_failed_count": d.get("recent_failed_count", classification.get("recent_failed_count", 0)),
            "historical_debt_total": d.get("historical_debt_total", 0),
            "stalest_pending": stalest,
            "metadata": d.get("metadata", {}),
        }

        failed = summary.get("failed", 0)
        pending = summary.get("pending", 0)
        recent_failed = d.get("recent_failed_count", classification.get("recent_failed_count", 0))
        gate_failed_delta = None if baseline_failed is None else max(0, int(failed or 0) - baseline_failed)
        historical_debt = d.get("historical_debt_total", 0)
        stale_pending = classification.get("stale_pending_debt_count", 0)
        orphan_running = classification.get("orphan_running_debt_count", 0)

        add_result("Queue: total", "PASS" if failed == 0 else "DEBT",
                   f"failed={failed}, pending={pending}, completed={summary.get('completed', 0)}")

        if historical_debt > 0:
            add_result("Queue: historical debt", "DEBT",
                       f"{historical_debt} failed tasks older than 1h")
        else:
            add_result("Queue: historical debt", "PASS", "no historical failed tasks")

        if gate_failed_delta is None:
            add_result("Queue: gate-run failed delta", "BLOCKER",
                       "missing pre-smoke failed baseline")
        elif gate_failed_delta > 0:
            add_result("Queue: gate-run failed delta", "BLOCKER",
                       f"failed increased during gate: {baseline_failed} -> {failed} (+{gate_failed_delta})")
        else:
            add_result("Queue: gate-run failed delta", "PASS",
                       f"no failed tasks added during gate: baseline={baseline_failed}, current={failed}")

        if recent_failed > 0:
            window_hours = d.get("metadata", {}).get("recent_failure_window_hours", "?")
            add_result("Queue: recent failed window", "DEBT",
                       f"{recent_failed} failed task(s) in the last {window_hours}h; tracked as debt unless gate delta grows")
        else:
            add_result("Queue: recent failed window", "PASS",
                       "no failed tasks in recent audit window")

        if stale_pending > 0:
            info = f"{stale_pending} stale pending (not new)"
            if stalest:
                info += f", oldest: type={stalest.get('task_type')} age={stalest.get('age_seconds')}s"
            add_result("Queue: stale pending", "DEBT",
                       info + " — not a BLOCKER because they predate current deploy")
        else:
            add_result("Queue: stale pending", "PASS", "no stale pending")

        if orphan_running > 0:
            add_result("Queue: orphan running", "DEBT",
                       f"{orphan_running} orphan running (not new)")
        else:
            add_result("Queue: orphan running", "PASS", "no orphan running")

        semantic_count, semantic_samples = find_semantic_failed_completed_tasks()
        semantic_level, semantic_detail = classify_semantic_failed_completed(
            semantic_count,
            baseline_semantic_failed_completed,
            semantic_samples,
        )
        add_result("Queue: semantic failed completed", semantic_level, semantic_detail)

    except Exception as e:
        add_result("Queue: audit", "BLOCKER", str(e))


def check_asset_lifecycle_debt() -> None:
    try:
        knowledge = audit_knowledge_lifecycle_debt()
        unavailable = int(knowledge.get("source_unavailable") or 0)
        level = "DEBT" if unavailable > 0 else "PASS"
        detail = (
            f"source_unavailable={unavailable}, source_recycled={knowledge.get('source_recycled', 0)}, "
            f"source_missing={knowledge.get('source_missing', 0)}"
        )
        runtime_context["knowledge_lifecycle_debt"] = knowledge
        add_result("Knowledge lifecycle debt", level, detail, knowledge)
    except Exception as exc:
        add_result("Knowledge lifecycle debt", "BLOCKER", str(exc))

    try:
        content = audit_content_package_lifecycle_debt()
        unavailable = int(content.get("source_unavailable") or 0)
        unarchived = int(content.get("unarchived_source_unavailable") or 0)
        missing_current = int(content.get("missing_current_version") or 0)
        if missing_current > 0:
            level = "BLOCKER"
        elif unarchived > 0:
            level = "DEBT"
        else:
            level = "PASS"
        detail = (
            f"source_unavailable={unavailable}, archived={content.get('archived_by_lifecycle', 0)}, "
            f"unarchived={unarchived}, missing_current_version={missing_current}"
        )
        runtime_context["content_package_lifecycle_debt"] = content
        add_result("ContentPackage lifecycle debt", level, detail, content)
    except Exception as exc:
        add_result("ContentPackage lifecycle debt", "BLOCKER", str(exc))

    try:
        pollution = audit_test_data_pollution()
        total = sum(
            int(pollution.get(key) or 0)
            for key in (
                "active_test_files",
                "recycled_test_files",
                "knowledge_documents_from_test_files",
                "content_packages_from_test_files",
            )
        )
        active = int(pollution.get("active_test_files") or 0)
        level = "BLOCKER" if total > 0 else "PASS"
        detail = (
            f"active={active}, recycled={pollution.get('recycled_test_files', 0)}, "
            f"knowledge={pollution.get('knowledge_documents_from_test_files', 0)}, "
            f"content={pollution.get('content_packages_from_test_files', 0)}"
        )
        runtime_context["test_data_pollution"] = pollution
        add_result("Test data pollution", level, detail, pollution)
    except Exception as exc:
        add_result("Test data pollution", "BLOCKER", str(exc))


async def check_capability_drift() -> None:
    try:
        live = await fetch_live_capabilities()
        level, detail, data = classify_capability_drift(live)
        runtime_context["capability_drift"] = data
        add_result("Capability drift", level, detail, data)
    except Exception as exc:
        add_result("Capability drift", "BLOCKER", str(exc))


def check_readme_acceptance_matrix() -> None:
    try:
        level, detail, data = classify_readme_acceptance_matrix()
        runtime_context["readme_acceptance_matrix"] = data
        add_result("README acceptance matrix", level, detail, data)
    except Exception as exc:
        add_result("README acceptance matrix", "BLOCKER", str(exc))


def check_component_key_contracts() -> None:
    try:
        level, detail, data = classify_component_key_contracts()
        runtime_context["component_key_contracts"] = data
        add_result("Component key contracts", level, detail, data)
    except Exception as exc:
        add_result("Component key contracts", "BLOCKER", str(exc))


async def check_sandbox_matrix(sandbox_jobs: int = 1, frontend_jobs: int = 1) -> None:
    """Run module_sandbox_matrix.py and report summary."""
    proc: asyncio.subprocess.Process | None = None
    try:
        started = time.monotonic()
        proc = await create_subprocess_exec_group(
            _project_python(),
            str(REPO_ROOT / "dev_toolkit" / "module_sandbox_matrix.py"),
            "--check", "--json",
            "--jobs", str(max(1, sandbox_jobs)),
            "--frontend-jobs", str(max(1, frontend_jobs)),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=REPO_ROOT,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        elapsed = time.monotonic() - started
        output = stdout.decode(errors="replace")

        if proc.returncode != 0 and proc.returncode != 1:
            add_result("Sandbox matrix", "BLOCKER",
                       f"script crashed (exit={proc.returncode})")
            return

        try:
            entries = json.loads(output)
        except json.JSONDecodeError:
            add_result("Sandbox matrix", "DEBT",
                       f"bad JSON output (len={len(output)}), see stderr")
            return

        level, detail = classify_sandbox_matrix(entries, elapsed)
        chunk_warning_modules = [
            str(e.get("module"))
            for e in entries
            if e.get("chunk_warnings")
            or any(result.get("chunk_warnings") for result in e.get("command_results", []) if isinstance(result, dict))
        ]
        runtime_context["sandbox_matrix"] = {
            "total": len(entries),
            "passed": sum(1 for e in entries if e.get("check") == "pass"),
            "failed": sum(1 for e in entries if e.get("check") == "fail"),
            "skipped": sum(1 for e in entries if e.get("check") == "skip"),
            "chunk_warning_count": len(chunk_warning_modules),
            "chunk_warning_modules": chunk_warning_modules[:10],
            "duration_seconds": round(elapsed, 3),
            "jobs": sandbox_jobs,
            "frontend_jobs": frontend_jobs,
        }
        add_result("Sandbox matrix", level, detail)
    except asyncio.TimeoutError:
        if proc is not None:
            await terminate_process_tree(proc)
        add_result("Sandbox matrix", "BLOCKER", "timeout (>180s)")
    except asyncio.CancelledError:
        if proc is not None:
            await terminate_process_tree(proc)
        raise
    except Exception as e:
        add_result("Sandbox matrix", "BLOCKER", str(e))


def get_final_verdict() -> str:
    blockers = [r for r in results if r["level"] == "BLOCKER"]
    debts = [r for r in results if r["level"] in {"DEBT", "SKIPPED_WITH_REASON"}]
    if blockers:
        return "BLOCKER"
    if debts:
        return "PASS_WITH_DEBT"
    return "PASS"


def _compact_items(levels: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "check": str(item.get("check", "")),
            "level": str(item.get("level", "")),
            "detail": str(item.get("detail", ""))[:300],
        }
        for item in results
        if item.get("level") in levels
    ]


def build_release_summary(verdict: str, *, skip_ui: bool = False, preflight: bool = False) -> dict[str, Any]:
    levels: dict[str, int] = {}
    for result in results:
        level = result["level"]
        levels[level] = levels.get(level, 0) + 1
    summary_verdict = "PASS_WITH_DEBT" if (skip_ui or preflight) and verdict == "PASS" else verdict
    has_debt = (
        skip_ui
        or preflight
        or levels.get("DEBT", 0) > 0
        or levels.get("SKIPPED_WITH_REASON", 0) > 0
    )
    clean_pass = summary_verdict == "PASS" and not skip_ui and not preflight
    clean_release_ready = clean_pass and not has_debt
    release_safe = summary_verdict in {"PASS", "PASS_WITH_DEBT"}
    deploy_allowed = release_safe
    blockers = _compact_items({"BLOCKER"})
    debts = _compact_items({"DEBT", "SKIPPED_WITH_REASON"})
    ui_coverage_status = runtime_context.get("ui_coverage", {})
    model_fallback_status = runtime_context.get("model_fallback", {})
    compact_summary = {
        "verdict": summary_verdict,
        "blockers": blockers,
        "debts": debts,
        "release_safe": release_safe,
        "clean_release_ready": clean_release_ready,
        "deploy_allowed": deploy_allowed,
        "ui_coverage_status": ui_coverage_status,
        "model_fallback_status": model_fallback_status,
    }
    return {
        "verdict": summary_verdict,
        "blockers": blockers,
        "debts": debts,
        "compact_summary": compact_summary,
        "clean_pass": clean_pass,
        "clean_release_ready": clean_release_ready,
        "release_safe": release_safe,
        "deploy_allowed": deploy_allowed,
        "ui_coverage_status": ui_coverage_status,
        "model_fallback_status": model_fallback_status,
        "has_debt": has_debt,
        "ui_skipped": skip_ui,
        "preflight": preflight,
        "gate_mode": "preflight" if preflight else ("backend_preflight" if skip_ui else "full_release"),
        "context": runtime_context,
        "levels": levels,
        "results": results,
    }


async def main():
    parser = argparse.ArgumentParser(description="Release gate validation")
    parser.add_argument("--skip-ui", action="store_true",
                        help="Skip Playwright UI tests in smoke_all")
    parser.add_argument("--preflight", action="store_true",
                        help="Run fast health/status/queue checks only; skip smoke and sandbox matrix")
    parser.add_argument("--sandbox-jobs", type=int, default=int(RELEASE_GATE_CONFIG.get("sandbox_jobs", 1) or 1),
                        help="Pass-through concurrency for module_sandbox_matrix --jobs")
    parser.add_argument(
        "--sandbox-frontend-jobs",
        type=int,
        default=int(RELEASE_GATE_CONFIG.get("sandbox_frontend_jobs", 1) or 1),
        help="Pass-through concurrency for module_sandbox_matrix --frontend-jobs",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  RELEASE GATE")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Backend: {BACKEND_BASE}")
    print("=" * 70)

    await collect_runtime_context()
    git_info = runtime_context.get("git", {})
    if git_info.get("dirty"):
        add_result(
            "Git worktree",
            "DEBT",
            f"dirty files={git_info.get('dirty_count', 0)}; included in machine JSON",
        )
    else:
        add_result("Git worktree", "PASS", f"clean sha={git_info.get('short_sha', '')}")
    frontend_state = runtime_context.get("services", {}).get("frontend", {})
    add_result(
        "Frontend availability",
        "PASS" if frontend_state.get("available") else "DEBT",
        f"{FRONTEND_BASE} status={frontend_state.get('status_code', frontend_state.get('error', 'unknown'))}",
    )
    print()
    await check_health()
    print()
    await check_system_status()
    print()
    baseline_failed: int | None = None
    baseline_semantic_failed_completed: int | None = None
    try:
        baseline_failed = audit_failed_count(await fetch_task_queue_audit())
        add_result("Queue: pre-smoke baseline", "PASS", f"failed={baseline_failed}")
    except Exception as e:
        add_result("Queue: pre-smoke baseline", "BLOCKER", str(e))
    try:
        baseline_semantic_failed_completed, _ = find_semantic_failed_completed_tasks()
        level = "DEBT" if baseline_semantic_failed_completed > 0 else "PASS"
        add_result(
            "Queue: pre-smoke semantic baseline",
            level,
            f"semantic_failed_completed={baseline_semantic_failed_completed}",
        )
    except Exception as e:
        add_result("Queue: pre-smoke semantic baseline", "BLOCKER", str(e))
    print()
    check_ui_coverage(skip_ui=args.skip_ui)
    print()
    if args.preflight:
        add_result("Smoke test (backends)", "DEBT", "--preflight used; smoke_all not run")
        runtime_context["ui_coverage"] = {
            "status": "DEBT",
            "included": False,
            "reason": "--preflight used; Playwright not run",
        }
        add_result("UI Playwright summary", "DEBT", "--preflight used; Playwright not run")
        runtime_context["model_fallback"] = {
            "status": "DEBT",
            "reason": "--preflight used; model fallback probe not run",
        }
        add_result("Model fallback", "DEBT", "--preflight used; model fallback probe not run")
    else:
        await check_smoke(skip_ui=args.skip_ui)
        _token_cache.clear()
    print()
    await check_task_queue_audit(baseline_failed, baseline_semantic_failed_completed)
    print()
    check_asset_lifecycle_debt()
    print()
    await check_capability_drift()
    print()
    check_readme_acceptance_matrix()
    print()
    check_component_key_contracts()
    print()
    if args.preflight:
        add_result("Sandbox matrix", "DEBT", "--preflight used; sandbox matrix not run")
    else:
        await check_sandbox_matrix(args.sandbox_jobs, args.sandbox_frontend_jobs)

    print()
    print("=" * 70)
    verdict = get_final_verdict()
    if args.preflight and verdict == "PASS":
        verdict = "PASS_WITH_DEBT"
    print(f"  RELEASE GATE VERDICT: {verdict}")
    print("=" * 70)
    print(
        "RELEASE_GATE_JSON: "
        + json.dumps(build_release_summary(verdict, skip_ui=args.skip_ui, preflight=args.preflight), ensure_ascii=False)
    )
    print()
    print(f"{'Check':<40} {'Level':>20}  Detail")
    print("-" * 100)
    for r in results:
        print(f"{r['check']:<40} {r['level']:>20}  {r['detail'][:120]}")

    print()
    if verdict == "BLOCKER":
        blockers = [r for r in results if r["level"] == "BLOCKER"]
        print(f"🔴 BLOCKERS ({len(blockers)}):")
        for b in blockers:
            print(f"  - {b['check']}: {b['detail'][:200]}")
        sys.exit(1)
    elif verdict == "PASS_WITH_DEBT":
        debts = [r for r in results if r["level"] in {"DEBT", "SKIPPED_WITH_REASON"}]
        print(f"🟡 DEBTS ({len(debts)}):")
        for d in debts:
            print(f"  - {d['check']}: {d['detail'][:200]}")
        print("✅ No BLOCKERs — release is safe with tracked debt.")
    else:
        print("✅ ALL CHECKS PASS — ready for release!")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--semantic-scan-json":
        scan_count, scan_samples = find_semantic_failed_completed_tasks(int(sys.argv[2]))
        print(json.dumps({"count": scan_count, "samples": scan_samples}, ensure_ascii=False))
        raise SystemExit(0)
    asyncio.run(main())
