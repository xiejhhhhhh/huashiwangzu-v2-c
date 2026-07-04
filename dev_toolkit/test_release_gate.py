"""Tests for release_gate.py — check level classification logic."""
import os
import subprocess
import sys
from pathlib import Path

import anyio
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dev_toolkit import release_gate  # noqa: E402

GATE_SCRIPT = REPO_ROOT / "dev_toolkit" / "release_gate.py"
BACKEND_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"


def _run(args: list[str], *, timeout: int = 360) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(BACKEND_PYTHON), str(GATE_SCRIPT), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def release_gate_preflight() -> subprocess.CompletedProcess:
    return _run(["--skip-ui", "--preflight"], timeout=120)


def test_help_output() -> None:
    r = subprocess.run(
        [str(BACKEND_PYTHON), str(GATE_SCRIPT), "--help"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0
    assert "usage:" in r.stdout.lower()
    assert "--preflight" in r.stdout


def test_release_gate_cli_preflight_runs_with_skip_ui(
    release_gate_preflight: subprocess.CompletedProcess,
) -> None:
    """--skip-ui --preflight should complete without heavy smoke/sandbox checks."""
    r = release_gate_preflight
    assert r.returncode in (0, 1), f"exit={r.returncode}, stderr={r.stderr[:1000]}"
    assert "RELEASE GATE VERDICT" in r.stdout
    assert "Health check" in r.stdout
    assert "Queue:" in r.stdout
    assert "Sandbox matrix" in r.stdout
    summary = release_gate.parse_prefixed_json(r.stdout, "RELEASE_GATE_JSON:")
    assert summary is not None
    assert summary["gate_mode"] == "preflight"
    assert summary["preflight"] is True
    assert summary["ui_skipped"] is True
    # Even on failure, the output should be properly formatted
    output = r.stdout
    if r.returncode == 0:
        assert "ALL CHECKS PASS" in output or "No BLOCKER" in output or "PASS_WITH_DEBT" in output


def test_preflight_output_contains_levels(
    release_gate_preflight: subprocess.CompletedProcess,
) -> None:
    """Each check should have a PASS/BLOCKER/DEBT/SKIPPED level."""
    r = release_gate_preflight
    for level in ("PASS", "BLOCKER", "DEBT", "SKIPPED_WITH_REASON"):
        if level in r.stdout:
            return
    # At least one of these should be present
    raise AssertionError(f"no expected level found in output: {r.stdout[:500]}")


@pytest.mark.slow
@pytest.mark.integration
def test_release_gate_full_skip_ui_is_opt_in() -> None:
    """Full --skip-ui gate is intentionally slow and never runs in ordinary pytest."""
    if os.environ.get("RUN_FULL_RELEASE_GATE") != "1":
        pytest.skip("set RUN_FULL_RELEASE_GATE=1 to run the full --skip-ui release gate")
    r = _run(["--skip-ui"])
    assert r.returncode in (0, 1), f"exit={r.returncode}, stderr={r.stderr[:1000]}"
    assert "RELEASE GATE VERDICT" in r.stdout
    assert "Smoke test (backends)" in r.stdout
    assert "Sandbox matrix" in r.stdout


def test_final_verdict_distinguishes_clean_pass_from_debt() -> None:
    original = list(release_gate.results)
    try:
        release_gate.results[:] = [{"check": "clean", "level": "PASS", "detail": "ok"}]
        assert release_gate.get_final_verdict() == "PASS"

        release_gate.results[:] = [{"check": "debt", "level": "DEBT", "detail": "tracked"}]
        assert release_gate.get_final_verdict() == "PASS_WITH_DEBT"

        release_gate.results[:] = [{"check": "skip", "level": "SKIPPED_WITH_REASON", "detail": "skipped"}]
        assert release_gate.get_final_verdict() == "PASS_WITH_DEBT"

        release_gate.results[:] = [{"check": "blocker", "level": "BLOCKER", "detail": "bad"}]
        assert release_gate.get_final_verdict() == "BLOCKER"
    finally:
        release_gate.results[:] = original


def test_sandbox_matrix_skips_are_debt_not_clean_pass() -> None:
    level, detail = release_gate.classify_sandbox_matrix(
        [{"module": "agent", "check": "pass"}, {"module": "missing-tests", "check": "skip"}],
        elapsed=1.2,
    )
    assert level == "DEBT"
    assert "skip" in detail


def test_project_python_prefers_backend_venv_then_current_interpreter(tmp_path, monkeypatch) -> None:
    backend_python = tmp_path / "backend-python"
    backend_python.write_text("", encoding="utf-8")
    fallback_python = tmp_path / "current-python"

    monkeypatch.setattr(release_gate, "BACKEND_PYTHON", backend_python)
    monkeypatch.setattr(release_gate.sys, "executable", str(fallback_python))
    assert release_gate._project_python() == str(backend_python)

    monkeypatch.setattr(release_gate, "BACKEND_PYTHON", tmp_path / "missing-python")
    assert release_gate._project_python() == str(fallback_python)


def test_probe_refreshes_token_once_on_401(monkeypatch) -> None:
    token_calls = []

    async def fake_ensure_token(*, force_refresh: bool = False) -> str:
        token_calls.append(force_refresh)
        return "fresh-token" if force_refresh else "stale-token"

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, method, path, json=None, headers=None):
            self.calls += 1
            if self.calls == 1:
                assert headers["Authorization"] == "Bearer stale-token"
                return FakeResponse(401, {"success": False, "error": "expired"})
            assert headers["Authorization"] == "Bearer fresh-token"
            return FakeResponse(200, {"success": True, "data": {"ok": True}})

    monkeypatch.setattr(release_gate, "_ensure_token", fake_ensure_token)
    monkeypatch.setattr(release_gate.httpx, "AsyncClient", FakeClient)

    result = anyio.run(release_gate.probe, "GET", "/api/tasks/worker/audit")
    assert result == {"success": True, "data": {"ok": True}}
    assert token_calls == [False, True]


def test_skip_ui_marks_release_summary_as_debt() -> None:
    original = list(release_gate.results)
    try:
        release_gate.results[:] = [{"check": "clean", "level": "PASS", "detail": "ok"}]
        direct_summary = release_gate.build_release_summary("PASS", skip_ui=True)
        assert direct_summary["verdict"] == "PASS_WITH_DEBT"
        assert direct_summary["has_debt"] is True

        preflight_summary = release_gate.build_release_summary("PASS", preflight=True)
        assert preflight_summary["verdict"] == "PASS_WITH_DEBT"
        assert preflight_summary["clean_pass"] is False
        assert preflight_summary["clean_release_ready"] is False
        assert preflight_summary["release_safe"] is True
        assert preflight_summary["has_debt"] is True
        assert preflight_summary["gate_mode"] == "preflight"

        release_gate.check_ui_coverage(skip_ui=True)
        verdict = release_gate.get_final_verdict()
        summary = release_gate.build_release_summary(verdict, skip_ui=True)

        assert verdict == "PASS_WITH_DEBT"
        assert summary["clean_pass"] is False
        assert summary["clean_release_ready"] is False
        assert summary["release_safe"] is True
        assert summary["has_debt"] is True
        assert summary["ui_skipped"] is True
        assert summary["gate_mode"] == "backend_preflight"
    finally:
        release_gate.results[:] = original


def test_preflight_does_not_run_smoke_or_sandbox(monkeypatch) -> None:
    original = list(release_gate.results)
    try:
        release_gate.results[:] = []

        async def fake_check_health() -> None:
            release_gate.add_result("Health check", "PASS", "ok")

        async def fake_check_system_status() -> None:
            release_gate.add_result("System status", "PASS", "ok")

        async def fake_fetch_task_queue_audit() -> dict:
            return {
                "summary": {"failed": 0, "pending": 0, "completed": 0},
                "classification": {},
                "recent_failed_count": 0,
                "historical_debt_total": 0,
                "metadata": {},
            }

        async def forbidden_smoke(_skip_ui: bool) -> None:
            raise AssertionError("preflight must not run smoke")

        async def forbidden_sandbox() -> None:
            raise AssertionError("preflight must not run sandbox")

        def fake_asset_lifecycle_debt() -> None:
            release_gate.add_result("Knowledge lifecycle debt", "PASS", "ok", {"source_unavailable": 0})
            release_gate.add_result("ContentPackage lifecycle debt", "PASS", "ok", {"source_unavailable": 0})
            release_gate.add_result("Test data pollution", "PASS", "ok", {"active_test_files": 0})

        monkeypatch.setattr(sys, "argv", ["release_gate.py", "--preflight"])
        monkeypatch.setattr(release_gate, "check_health", fake_check_health)
        monkeypatch.setattr(release_gate, "check_system_status", fake_check_system_status)
        monkeypatch.setattr(release_gate, "fetch_task_queue_audit", fake_fetch_task_queue_audit)
        monkeypatch.setattr(release_gate, "find_semantic_failed_completed_tasks", lambda *_args, **_kwargs: (0, []))
        monkeypatch.setattr(release_gate, "check_smoke", forbidden_smoke)
        monkeypatch.setattr(release_gate, "check_sandbox_matrix", forbidden_sandbox)
        monkeypatch.setattr(release_gate, "check_asset_lifecycle_debt", fake_asset_lifecycle_debt)

        anyio.run(release_gate.main)

        summary = release_gate.build_release_summary(
            release_gate.get_final_verdict(),
            preflight=True,
        )
        checks = {item["check"]: item for item in release_gate.results}
        assert checks["Smoke test (backends)"]["level"] == "DEBT"
        assert checks["Sandbox matrix"]["level"] == "DEBT"
        assert summary["gate_mode"] == "preflight"
        assert summary["clean_pass"] is False
        assert summary["clean_release_ready"] is False
    finally:
        release_gate.results[:] = original


def test_parse_prefixed_json_extracts_machine_summary() -> None:
    output = 'noise\nRELEASE_GATE_JSON: {"verdict": "PASS_WITH_DEBT", "has_debt": true}\n'
    assert release_gate.parse_prefixed_json(output, "RELEASE_GATE_JSON:") == {
        "verdict": "PASS_WITH_DEBT",
        "has_debt": True,
    }


def test_audit_failed_count_fails_closed_on_missing_summary() -> None:
    try:
        release_gate.audit_failed_count({"success": True, "data": {}})
    except ValueError as exc:
        assert "summary.failed" in str(exc)
        return
    raise AssertionError("missing summary.failed should not default to zero")


def test_task_result_semantic_failure_contract() -> None:
    assert release_gate._task_result_is_semantic_failure({"success": False, "error": "bad"}) == (
        True,
        "bad",
    )
    assert release_gate._task_result_is_semantic_failure({"status": "failed"}) == (
        True,
        "Task result status=failed",
    )
    assert release_gate._task_result_is_semantic_failure({"error": "bad"}) == (True, "bad")
    assert release_gate._task_result_is_semantic_failure({"status": "skipped", "reason": "empty"}) == (
        False,
        None,
    )
    assert release_gate._task_result_is_semantic_failure({"success": True, "error": "legacy-note"}) == (
        False,
        None,
    )


def test_semantic_failed_completed_delta_is_blocker_only_for_new_growth() -> None:
    level, detail = release_gate.classify_semantic_failed_completed(3, 3)
    assert level == "DEBT"
    assert "historical" in detail

    level, detail = release_gate.classify_semantic_failed_completed(
        4,
        3,
        [{"id": 12, "task_type": "memory_distill"}],
    )
    assert level == "BLOCKER"
    assert "3 -> 4" in detail
    assert "#12:memory_distill" in detail

    assert release_gate.classify_semantic_failed_completed(0, 0)[0] == "PASS"
    assert release_gate.classify_semantic_failed_completed(0, None)[0] == "BLOCKER"


def test_release_summary_keeps_result_data_and_clean_release_ready() -> None:
    original = list(release_gate.results)
    try:
        release_gate.results[:] = []
        release_gate.add_result("Knowledge lifecycle debt", "DEBT", "source_unavailable=1", {"source_unavailable": 1})
        summary = release_gate.build_release_summary("PASS_WITH_DEBT")

        assert summary["clean_pass"] is False
        assert summary["clean_release_ready"] is False
        assert summary["release_safe"] is True
        assert summary["results"][0]["data"] == {"source_unavailable": 1}
    finally:
        release_gate.results[:] = original


def test_asset_lifecycle_gate_classification(monkeypatch) -> None:
    original_results = list(release_gate.results)
    original_context = dict(release_gate.runtime_context)
    try:
        release_gate.results[:] = []
        release_gate.runtime_context.clear()
        monkeypatch.setattr(
            release_gate,
            "audit_knowledge_lifecycle_debt",
            lambda: {"source_unavailable": 2, "source_recycled": 2, "source_missing": 0},
        )
        monkeypatch.setattr(
            release_gate,
            "audit_content_package_lifecycle_debt",
            lambda: {"source_unavailable": 3, "archived_by_lifecycle": 1, "missing_current_version": 0},
        )
        monkeypatch.setattr(
            release_gate,
            "audit_test_data_pollution",
            lambda: {
                "active_test_files": 0,
                "recycled_test_files": 4,
                "knowledge_documents_from_test_files": 1,
                "content_packages_from_test_files": 1,
            },
        )

        release_gate.check_asset_lifecycle_debt()
        checks = {item["check"]: item for item in release_gate.results}

        assert checks["Knowledge lifecycle debt"]["level"] == "DEBT"
        assert checks["ContentPackage lifecycle debt"]["level"] == "DEBT"
        assert checks["Test data pollution"]["level"] == "DEBT"
        assert release_gate.runtime_context["knowledge_lifecycle_debt"]["source_unavailable"] == 2
    finally:
        release_gate.results[:] = original_results
        release_gate.runtime_context.clear()
        release_gate.runtime_context.update(original_context)


if __name__ == "__main__":
    test_help_output()
    preflight = _run(["--skip-ui", "--preflight"], timeout=120)
    test_release_gate_cli_preflight_runs_with_skip_ui(preflight)
    test_preflight_output_contains_levels(preflight)
    test_final_verdict_distinguishes_clean_pass_from_debt()
    test_sandbox_matrix_skips_are_debt_not_clean_pass()
    test_skip_ui_marks_release_summary_as_debt()
    test_parse_prefixed_json_extracts_machine_summary()
    test_audit_failed_count_fails_closed_on_missing_summary()
    test_task_result_semantic_failure_contract()
    test_semantic_failed_completed_delta_is_blocker_only_for_new_growth()
    print("\nAll release gate tests PASS")
