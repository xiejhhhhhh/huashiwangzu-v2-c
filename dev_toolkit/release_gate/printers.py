"""Human and machine-output helpers for the release gate."""
from __future__ import annotations

from typing import Any

from .context import results, runtime_context


def add_result(check: str, level: str, detail: str, data: dict[str, Any] | None = None) -> None:
    item = {"check": check, "level": level, "detail": detail}
    if data is not None:
        item["data"] = data
    results.append(item)
    icon = {"PASS": "✅", "BLOCKER": "🔴", "DEBT": "🟡", "SKIPPED_WITH_REASON": "⏭️"}.get(level, "❓")
    print(f"  {icon} [{level:>20}] {check}: {detail[:200]}")

def get_final_verdict() -> str:
    blockers = [r for r in results if r["level"] == "BLOCKER"]
    debts = [r for r in results if r["level"] in {"DEBT", "SKIPPED_WITH_REASON"}]
    if blockers:
        return "BLOCKED"
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
    blockers = _compact_items({"BLOCKER"})
    debts = _compact_items({"DEBT", "SKIPPED_WITH_REASON"})
    has_blockers = bool(blockers) or verdict in {"BLOCKED", "BLOCKER"}
    if has_blockers:
        summary_verdict = "BLOCKED"
    elif (skip_ui or preflight) and verdict == "PASS":
        summary_verdict = "PASS_WITH_DEBT"
    else:
        summary_verdict = verdict
    has_debt = (
        skip_ui
        or preflight
        or levels.get("DEBT", 0) > 0
        or levels.get("SKIPPED_WITH_REASON", 0) > 0
    )
    clean_pass = summary_verdict == "PASS" and not skip_ui and not preflight and not has_debt and not has_blockers
    clean_release_ready = clean_pass and not has_debt
    release_safe = summary_verdict in {"PASS", "PASS_WITH_DEBT"} and not has_blockers
    deploy_allowed = release_safe
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
