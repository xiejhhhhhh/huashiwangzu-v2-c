"""CLI orchestration for the release gate."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from dev_toolkit.release_gate_support import find_semantic_failed_completed_tasks

from . import checks, smoke_gate
from .context import (
    BACKEND_BASE,
    FRONTEND_BASE,
    RELEASE_GATE_CONFIG,
    _token_cache,
    audit_failed_count,
    collect_runtime_context,
    fetch_task_queue_audit,
    results,
    runtime_context,
)
from .printers import add_result, build_release_summary, get_final_verdict


def _default_api() -> SimpleNamespace:
    return SimpleNamespace(
        BACKEND_BASE=BACKEND_BASE,
        FRONTEND_BASE=FRONTEND_BASE,
        RELEASE_GATE_CONFIG=RELEASE_GATE_CONFIG,
        _token_cache=_token_cache,
        add_result=add_result,
        audit_failed_count=audit_failed_count,
        build_release_summary=build_release_summary,
        check_asset_lifecycle_debt=checks.check_asset_lifecycle_debt,
        check_capability_drift=checks.check_capability_drift,
        check_component_key_contracts=checks.check_component_key_contracts,
        check_docs_currentness=checks.check_docs_currentness,
        check_health=checks.check_health,
        check_model_fallback_summary=smoke_gate.check_model_fallback_summary,
        check_readme_acceptance_matrix=checks.check_readme_acceptance_matrix,
        check_sandbox_matrix=checks.check_sandbox_matrix,
        check_smoke=smoke_gate.check_smoke,
        check_system_status=checks.check_system_status,
        check_task_queue_audit=checks.check_task_queue_audit,
        check_ui_coverage=smoke_gate.check_ui_coverage,
        collect_runtime_context=collect_runtime_context,
        fetch_task_queue_audit=fetch_task_queue_audit,
        find_semantic_failed_completed_tasks=find_semantic_failed_completed_tasks,
        get_final_verdict=get_final_verdict,
        runtime_context=runtime_context,
    )


async def main(argv: list[str] | None = None, *, api: Any | None = None) -> None:
    api = api or _default_api()
    parser = argparse.ArgumentParser(description="Release gate validation")
    parser.add_argument("--skip-ui", action="store_true", help="Skip Playwright UI tests in smoke_all")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Run fast health/status/queue checks only; skip smoke and sandbox matrix",
    )
    parser.add_argument(
        "--sandbox-jobs",
        type=int,
        default=int(api.RELEASE_GATE_CONFIG.get("sandbox_jobs", 1) or 1),
        help="Pass-through concurrency for module_sandbox_matrix --jobs",
    )
    parser.add_argument(
        "--sandbox-frontend-jobs",
        type=int,
        default=int(api.RELEASE_GATE_CONFIG.get("sandbox_frontend_jobs", 1) or 1),
        help="Pass-through concurrency for module_sandbox_matrix --frontend-jobs",
    )
    args = parser.parse_args(argv)

    print("=" * 70)
    print("  RELEASE GATE")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Backend: {api.BACKEND_BASE}")
    print("=" * 70)

    await api.collect_runtime_context()
    git_info = api.runtime_context.get("git", {})
    if git_info.get("dirty"):
        api.add_result(
            "Git worktree",
            "DEBT",
            f"dirty files={git_info.get('dirty_count', 0)}; included in machine JSON",
        )
    else:
        api.add_result("Git worktree", "PASS", f"clean sha={git_info.get('short_sha', '')}")
    frontend_state = api.runtime_context.get("services", {}).get("frontend", {})
    api.add_result(
        "Frontend availability",
        "PASS" if frontend_state.get("available") else "DEBT",
        f"{api.FRONTEND_BASE} status={frontend_state.get('status_code', frontend_state.get('error', 'unknown'))}",
    )
    print()
    await api.check_health()
    print()
    await api.check_system_status()
    print()
    baseline_failed: int | None = None
    baseline_semantic_failed_completed: int | None = None
    try:
        baseline_failed = api.audit_failed_count(await api.fetch_task_queue_audit())
        api.add_result("Queue: pre-smoke baseline", "PASS", f"failed={baseline_failed}")
    except Exception as e:
        api.add_result("Queue: pre-smoke baseline", "BLOCKER", str(e))
    try:
        baseline_semantic_failed_completed, _ = api.find_semantic_failed_completed_tasks()
        level = "DEBT" if baseline_semantic_failed_completed > 0 else "PASS"
        api.add_result(
            "Queue: pre-smoke semantic baseline",
            level,
            f"semantic_failed_completed={baseline_semantic_failed_completed}",
        )
    except Exception as e:
        api.add_result("Queue: pre-smoke semantic baseline", "BLOCKER", str(e))
    print()
    api.check_ui_coverage(skip_ui=args.skip_ui)
    print()
    if args.preflight:
        api.add_result("Smoke test (backends)", "DEBT", "--preflight used; smoke_all not run")
        api.runtime_context["ui_coverage"] = {
            "status": "DEBT",
            "included": False,
            "reason": "--preflight used; Playwright not run",
        }
        api.add_result("UI Playwright summary", "DEBT", "--preflight used; Playwright not run")
        api.runtime_context["model_fallback"] = {
            "status": "DEBT",
            "reason": "--preflight used; model fallback probe not run",
        }
        api.add_result("Model fallback", "DEBT", "--preflight used; model fallback probe not run")
    else:
        await api.check_smoke(skip_ui=args.skip_ui)
        api._token_cache.clear()
    print()
    await api.check_task_queue_audit(baseline_failed, baseline_semantic_failed_completed)
    print()
    api.check_asset_lifecycle_debt()
    print()
    await api.check_capability_drift()
    print()
    api.check_readme_acceptance_matrix()
    print()
    api.check_component_key_contracts()
    print()
    api.check_docs_currentness()
    print()
    if args.preflight:
        api.add_result("Sandbox matrix", "DEBT", "--preflight used; sandbox matrix not run")
    else:
        await api.check_sandbox_matrix(args.sandbox_jobs, args.sandbox_frontend_jobs)

    print()
    print("=" * 70)
    verdict = api.get_final_verdict()
    if args.preflight and verdict == "PASS":
        verdict = "PASS_WITH_DEBT"
    print(f"  RELEASE GATE VERDICT: {verdict}")
    print("=" * 70)
    print(
        "RELEASE_GATE_JSON: "
        + json.dumps(api.build_release_summary(verdict, skip_ui=args.skip_ui, preflight=args.preflight), ensure_ascii=False)
    )
    print()
    print(f"{'Check':<40} {'Level':>20}  Detail")
    print("-" * 100)
    for r in results:
        print(f"{r['check']:<40} {r['level']:>20}  {r['detail'][:120]}")

    print()
    if verdict == "BLOCKED":
        blockers = [r for r in results if r["level"] == "BLOCKER"]
        print(f"🔴 BLOCKERS ({len(blockers)}):")
        for b in blockers:
            print(f"  - {b['check']}: {b['detail'][:200]}")
        sys.exit(1)
    if verdict == "PASS_WITH_DEBT":
        debts = [r for r in results if r["level"] in {"DEBT", "SKIPPED_WITH_REASON"}]
        print(f"🟡 DEBTS ({len(debts)}):")
        for d in debts:
            print(f"  - {d['check']}: {d['detail'][:200]}")
        print("✅ No BLOCKERs — release is safe with tracked debt.")
    else:
        print("✅ ALL CHECKS PASS — ready for release!")


def cli_main(argv: list[str] | None = None, *, api: Any | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "--semantic-scan-json":
        scan_count, scan_samples = find_semantic_failed_completed_tasks(int(argv[1]))
        print(json.dumps({"count": scan_count, "samples": scan_samples}, ensure_ascii=False))
        raise SystemExit(0)
    asyncio.run(main(argv, api=api))
