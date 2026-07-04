"""Machine-readable release gate response helpers."""
import json
from typing import Any


def extract_prefixed_json(output: str, prefix: str) -> dict[str, Any] | None:
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


def tail_text(text: str, limit: int = 20000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def build_release_gate_response(
    output: str,
    returncode: int,
    skip_ui: bool,
    duration_seconds: float,
) -> dict[str, Any]:
    summary = extract_prefixed_json(output, "RELEASE_GATE_JSON:")
    if summary is None:
        return {
            "success": False,
            "clean_pass": False,
            "clean_release_ready": False,
            "release_safe": False,
            "deploy_allowed": False,
            "has_debt": False,
            "verdict": "INVALID_GATE_OUTPUT",
            "returncode": returncode,
            "skip_ui": skip_ui,
            "ui_skipped": skip_ui,
            "gate_mode": "invalid_output",
            "duration_seconds": round(duration_seconds, 3),
            "summary": None,
            "invalid_output": True,
            "output": output,
            "output_tail": tail_text(output, 20000),
        }

    verdict = summary.get("verdict")
    if not isinstance(verdict, str) or not verdict:
        verdict = "INVALID_GATE_OUTPUT"
    summary_ui_skipped = bool(summary.get("ui_skipped"))
    ui_skipped = skip_ui or summary_ui_skipped
    if ui_skipped and returncode == 0 and verdict == "PASS":
        verdict = "PASS_WITH_DEBT"
    summary_has_debt = bool(summary.get("has_debt"))
    summary_clean_pass = summary.get("clean_pass")
    clean_pass = (
        returncode == 0
        and verdict == "PASS"
        and not ui_skipped
        and not summary_has_debt
        and summary_clean_pass is not False
    )
    release_safe = returncode == 0 and verdict in {"PASS", "PASS_WITH_DEBT"}
    deploy_allowed = release_safe
    has_debt = summary_has_debt or verdict == "PASS_WITH_DEBT" or ui_skipped
    clean_release_ready = clean_pass and not has_debt and bool(summary.get("clean_release_ready", clean_pass))
    gate_mode = summary.get("gate_mode")
    if not isinstance(gate_mode, str) or not gate_mode:
        gate_mode = "backend_preflight" if ui_skipped else "full_release"
    return {
        "success": clean_pass,
        "clean_pass": clean_pass,
        "clean_release_ready": clean_release_ready,
        "release_safe": release_safe,
        "deploy_allowed": deploy_allowed,
        "has_debt": has_debt,
        "verdict": verdict,
        "returncode": returncode,
        "skip_ui": skip_ui,
        "ui_skipped": ui_skipped,
        "gate_mode": gate_mode,
        "duration_seconds": round(duration_seconds, 3),
        "summary": summary,
        "output": output,
        "output_tail": tail_text(output, 20000),
    }
