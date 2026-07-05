"""Pure helpers for release_gate.py.

Keep orchestration in release_gate.py and place data audits / classifiers here
so the gate entrypoint stays within the project file-size budget.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from dev_toolkit.config_loader import load_config
    from dev_toolkit.sql_guard import readonly_psql_env
except ModuleNotFoundError:
    from config_loader import load_config
    from sql_guard import readonly_psql_env

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULES_DIR = REPO_ROOT / "modules"
BACKEND_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"
CONFIG = load_config(REPO_ROOT)
DB_DSN = CONFIG.get("db_dsn", "")
SEMANTIC_COMPLETED_SCAN_LIMIT = 500


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
        [str(BACKEND_PYTHON), str(REPO_ROOT / "dev_toolkit" / "release_gate.py"), "--semantic-scan-json", str(limit)],
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
    changed_modules = changed_modules if changed_modules is not None else set()
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
            "INFO",
            f"{total} modules, {passed} pass, {skipped} skip, non-blocking chunk warnings in "
            f"{len(chunk_warning_modules)} ({', '.join(chunk_warning_modules[:5])}) ({elapsed:.0f}s)",
        )
    if skipped > 0:
        return "DEBT", f"{total} modules, {passed} pass, {skipped} skip ({elapsed:.0f}s) — skipped is tracked debt"
    return "PASS", f"{total} modules, {passed} pass, 0 skip ({elapsed:.0f}s)"
