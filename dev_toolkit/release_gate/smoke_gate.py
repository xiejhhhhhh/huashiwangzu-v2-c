"""Smoke, UI coverage, and model-fallback gate checks."""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

try:
    from dev_toolkit.process_tools import create_subprocess_exec_group, terminate_process_tree
    from dev_toolkit.release_gate_support import parse_prefixed_json
except ModuleNotFoundError:
    from process_tools import create_subprocess_exec_group, terminate_process_tree
    from release_gate_support import parse_prefixed_json

from .context import REPO_ROOT, _project_python, runtime_context
from .printers import add_result


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
    if status not in {"PASS", "DEBT", "BLOCKER"}:
        runtime_context["model_fallback"] = {
            "status": "BLOCKER",
            "reason": f"unknown model fallback status={status!r}",
        }
        add_result("Model fallback", "BLOCKER", f"unknown model fallback status={status!r}")
        return
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
