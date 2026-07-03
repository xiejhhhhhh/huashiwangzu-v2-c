"""Release gate — pre-publish validation matrix.

Aggregates:
  1. /api/health
  2. /api/system/status
  3. smoke_all(skip_ui=true)
  4. Task queue audit (gate-run additions vs historical debt)
  5. Module sandbox matrix summary

Output levels:
  - PASS       everything green
  - BLOCKER    must fix before release (gate-run failures, health non-ok, worker down)
  - DEBT       known historical issues, tracked not blocking
  - SKIPPED_WITH_REASON  intentionally skipped (e.g. no sandbox test)

Usage:
    cd <repo> && backend/.venv/bin/python dev_toolkit/release_gate.py [--skip-ui]
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"
BACKEND_BASE = "http://127.0.0.1:33000"
CONFIG_PATH = REPO_ROOT / "dev_toolkit" / "config.json"
SEMANTIC_COMPLETED_SCAN_LIMIT = 500

with open(CONFIG_PATH, encoding="utf-8") as f:
    CONFIG = json.load(f)
DB_DSN = CONFIG.get("db_dsn", "")

ACCOUNTS = {
    "admin": {"username": "何焜华", "password": "123rgE123"},
}

results: list[dict[str, Any]] = []
_token_cache: dict[str, tuple[str, float]] = {}
_TOKEN_MAX_AGE = 300  # 5 min — short enough to avoid stale-after-smoke expiry


def add_result(check: str, level: str, detail: str) -> None:
    results.append({"check": check, "level": level, "detail": detail})
    icon = {"PASS": "✅", "BLOCKER": "🔴", "DEBT": "🟡", "SKIPPED_WITH_REASON": "⏭️"}.get(level, "❓")
    print(f"  {icon} [{level:>20}] {check}: {detail[:200]}")


async def _ensure_token() -> str:
    now = time.monotonic()
    if "admin" in _token_cache:
        cached_token, cached_at = _token_cache["admin"]
        if now - cached_at < _TOKEN_MAX_AGE:
            return cached_token
    acct = ACCOUNTS["admin"]
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
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text[:500], "status": resp.status_code}


async def fetch_task_queue_audit() -> dict[str, Any]:
    r = await probe("GET", "/api/tasks/worker/audit")
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
    if not isinstance(result, dict):
        return False, None
    if result.get("success") is False:
        return True, str(result.get("error") or "Task result success=false")
    status = result.get("status")
    if isinstance(status, str) and status.lower() in {"failed", "error"}:
        return True, str(result.get("error") or f"Task result status={status}")
    if result.get("error") not in (None, "") and result.get("success") is not True:
        return True, str(result.get("error"))
    return False, None


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


def classify_sandbox_matrix(entries: list[dict[str, Any]], elapsed: float) -> tuple[str, str]:
    total = len(entries)
    passed = sum(1 for e in entries if e.get("check") == "pass")
    failed = sum(1 for e in entries if e.get("check") == "fail")
    skipped = sum(1 for e in entries if e.get("check") == "skip")

    if failed > 0:
        fail_names = [e["module"] for e in entries if e.get("check") == "fail"]
        return (
            "BLOCKER",
            f"{total} modules, {passed} pass, {failed} fail ({', '.join(fail_names)}), {skipped} skip ({elapsed:.0f}s)",
        )
    if skipped > 0:
        return "DEBT", f"{total} modules, {passed} pass, {skipped} skip ({elapsed:.0f}s) — skipped is tracked debt"
    return "PASS", f"{total} modules, {passed} pass, 0 skip ({elapsed:.0f}s)"


async def check_health() -> None:
    try:
        r = await probe("GET", "/api/health")
        d = r.get("data", r)
        status = d.get("status", "unknown")
        if status == "ok":
            add_result("Health check", "PASS", f"status={status}, db={d.get('database')}")
        else:
            add_result("Health check", "BLOCKER", f"status={status}, db={d.get('database')}")
    except Exception as e:
        add_result("Health check", "BLOCKER", str(e))


async def check_system_status() -> None:
    try:
        r = await probe("GET", "/api/system/status")
        d = r.get("data", r)
        backend_ok = d.get("backend", {}).get("status") is True
        db_ok = d.get("database", {}).get("status") is True
        worker_ok = d.get("worker", {}).get("status") is True
        if backend_ok and db_ok and worker_ok:
            add_result("System status", "PASS", "backend/db/worker all ok")
        else:
            failing = [k for k in ("backend", "database", "worker") if not d.get(k, {}).get("status")]
            add_result("System status", "BLOCKER", f"failing: {', '.join(failing)}")
    except Exception as e:
        add_result("System status", "BLOCKER", str(e))


async def check_smoke(skip_ui: bool) -> None:
    try:
        started = time.monotonic()
        env_override = {"SMOKE_SKIP_UI": "1"} if skip_ui else {}
        env = {**os.environ.copy(), **env_override}
        smoke_python = str(BACKEND_PYTHON if BACKEND_PYTHON.exists() else Path(sys.executable))
        proc = await asyncio.create_subprocess_exec(
            smoke_python,
            str(REPO_ROOT / "dev_toolkit" / "smoke.py"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=360)
        elapsed = time.monotonic() - started
        output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
        passed = proc.returncode == 0
        smoke_summary = parse_prefixed_json(output, "SMOKE_JSON:")

        if smoke_summary:
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
            return

        # Parse the red-green matrix footer
        total = "-"
        green = "-"
        red = "-"
        for line in output.splitlines():
            if "总计" in line or "Total" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p.isdigit():
                        if total == "-":
                            total = p
                        elif green == "-":
                            green = p
                        elif red == "-":
                            red = p
                            break
            if "全绿" in line or "All green" in line:
                red = "0"

        if passed and (red == "-" or red == "0" or red == "0"):
            add_result("Smoke test (backends)", "PASS",
                       f"{elapsed:.0f}s, all green")
        elif passed:
            add_result("Smoke test (backends)", "DEBT",
                       f"{elapsed:.0f}s, passed but red count uncertain, see raw output")
        else:
            # Extract failure count from output
            fail_lines = [line for line in output.splitlines() if "R]" in line or "❌" in line or "[R]" in line]
            add_result("Smoke test (backends)", "BLOCKER",
                       f"{elapsed:.0f}s, exit={proc.returncode}, failures: {len(fail_lines)}")
    except asyncio.TimeoutError:
        add_result("Smoke test (backends)", "BLOCKER", "timeout (>360s)")
    except Exception as e:
        add_result("Smoke test (backends)", "BLOCKER", str(e))


async def check_task_queue_audit(
    baseline_failed: int | None,
    baseline_semantic_failed_completed: int | None = None,
) -> None:
    try:
        d = await fetch_task_queue_audit()
        summary = d.get("summary", {})
        classification = d.get("classification", {})
        stalest = d.get("stalest_pending")

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


async def check_sandbox_matrix() -> None:
    """Run module_sandbox_matrix.py and report summary."""
    try:
        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(REPO_ROOT / "dev_toolkit" / "module_sandbox_matrix.py"),
            "--check", "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
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
        add_result("Sandbox matrix", level, detail)
    except asyncio.TimeoutError:
        add_result("Sandbox matrix", "BLOCKER", "timeout (>180s)")
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


def build_release_summary(verdict: str) -> dict[str, Any]:
    levels: dict[str, int] = {}
    for result in results:
        level = result["level"]
        levels[level] = levels.get(level, 0) + 1
    return {
        "verdict": verdict,
        "clean_pass": verdict == "PASS",
        "release_safe": verdict in {"PASS", "PASS_WITH_DEBT"},
        "has_debt": verdict == "PASS_WITH_DEBT",
        "levels": levels,
        "results": results,
    }


async def main():
    parser = argparse.ArgumentParser(description="Release gate validation")
    parser.add_argument("--skip-ui", action="store_true",
                        help="Skip Playwright UI tests in smoke_all")
    args = parser.parse_args()

    print("=" * 70)
    print("  RELEASE GATE")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Backend: {BACKEND_BASE}")
    print("=" * 70)

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
    await check_smoke(skip_ui=args.skip_ui)
    _token_cache.clear()
    print()
    await check_task_queue_audit(baseline_failed, baseline_semantic_failed_completed)
    print()
    await check_sandbox_matrix()

    print()
    print("=" * 70)
    verdict = get_final_verdict()
    print(f"  RELEASE GATE VERDICT: {verdict}")
    print("=" * 70)
    print("RELEASE_GATE_JSON: " + json.dumps(build_release_summary(verdict), ensure_ascii=False))
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
