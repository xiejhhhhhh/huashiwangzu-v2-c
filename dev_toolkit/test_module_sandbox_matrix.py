"""Tests for module_sandbox_matrix.py."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dev_toolkit import module_sandbox_matrix  # noqa: E402

MATRIX_SCRIPT = REPO_ROOT / "dev_toolkit" / "module_sandbox_matrix.py"
BACKEND_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(BACKEND_PYTHON), str(MATRIX_SCRIPT), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture(scope="module")
def matrix_results() -> list[dict]:
    return module_sandbox_matrix.scan_sandbox_matrix()


def test_scan_json_output(matrix_results: list[dict]) -> None:
    """Matrix entries should serialize to a valid JSON array."""
    data = json.loads(json.dumps(matrix_results, ensure_ascii=False))
    assert isinstance(data, list)
    assert len(data) > 0, "should have at least one module entry"
    required_keys = {"module", "has_sandbox", "has_test_module", "check", "reason"}
    for entry in data:
        assert required_keys.issubset(entry.keys()), f"missing keys in {entry['module']}"
    # All entries have a check status
    checks = {e["check"] for e in data}
    assert checks.issubset({"pass", "skip", "fail"}), f"unexpected check values: {checks}"


def test_cli_single_module_json_smoke() -> None:
    """Keep one subprocess smoke test for CLI wiring."""
    r = _run(["--json", "--module", "agent"])
    assert r.returncode == 0, f"exit={r.returncode}, stderr={r.stderr[:500]}"
    data = json.loads(r.stdout)
    assert [entry["module"] for entry in data] == ["agent"]


def test_markdown_output(matrix_results: list[dict]) -> None:
    """Default output should be markdown with a table."""
    output = module_sandbox_matrix.format_markdown(matrix_results, run_all=False, passed=True)
    assert "# Module Sandbox Verification Matrix" in output
    assert "| Module | Sandbox |" in output
    assert "README Acceptance" in output
    assert "**Summary**" in output


def test_scan_includes_known_modules(matrix_results: list[dict]) -> None:
    """Should find modules with sandboxes like agent, excel-engine, etc."""
    keys = [e["module"] for e in matrix_results]
    # At least a few known modules should be present
    found = {k for k in keys if k in {"agent", "excel-engine", "image-vision", "desktop-tools"}}
    assert len(found) >= 3, f"expected 3+ known modules, got {found}"


def test_agent_has_sandbox(matrix_results: list[dict]) -> None:
    """agent module should have a sandbox and backend."""
    agent = next((e for e in matrix_results if e["module"] == "agent"), None)
    assert agent is not None, "agent entry not found"
    assert agent["has_sandbox"] is True
    assert agent["has_backend"] is True


def test_excel_engine_has_test_module(matrix_results: list[dict]) -> None:
    """excel-engine should have test_module.py in sandbox."""
    ee = next((e for e in matrix_results if e["module"] == "excel-engine"), None)
    assert ee is not None
    assert ee["has_test_module"] is True, "excel-engine should have test_module.py"


def test_parser_help_mentions_targeted_options() -> None:
    help_text = module_sandbox_matrix.build_arg_parser().format_help()
    assert "--module" in help_text
    assert "--modules" in help_text
    assert "--jobs" in help_text


def test_parse_requested_modules_dedupes_in_order() -> None:
    assert module_sandbox_matrix.parse_requested_modules(
        ["agent", "agent"],
        "knowledge, excel-engine,knowledge",
    ) == ["agent", "knowledge", "excel-engine"]


def test_scan_can_target_multiple_modules() -> None:
    results = module_sandbox_matrix.scan_sandbox_matrix(["knowledge", "agent"])
    assert [entry["module"] for entry in results] == ["knowledge", "agent"]


def test_scan_rejects_unknown_module() -> None:
    with pytest.raises(ValueError, match="unknown module"):
        module_sandbox_matrix.scan_sandbox_matrix(["__missing_module__"])


def test_check_runs_frontend_build_command(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="built", stderr="")

    monkeypatch.setattr(module_sandbox_matrix.subprocess, "run", fake_run)
    entries = [{
        "module": "front-only",
        "check": "pass",
        "backend_test_cmd": None,
        "frontend_build_cmd": "cd modules/front-only/sandbox && npm run build",
    }]

    assert module_sandbox_matrix.check_sandbox_matrix(entries, quiet=True)
    assert entries[0]["check"] == "pass"
    assert calls[0][0] == ["npm", "run", "build"]
    assert calls[0][1]["cwd"] == REPO_ROOT / "modules/front-only/sandbox"


def test_check_fails_when_frontend_build_fails(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="vite failed")

    monkeypatch.setattr(module_sandbox_matrix.subprocess, "run", fake_run)
    entries = [{
        "module": "front-only",
        "check": "pass",
        "backend_test_cmd": None,
        "frontend_build_cmd": "cd modules/front-only/sandbox && npm run build",
    }]

    assert not module_sandbox_matrix.check_sandbox_matrix(entries, quiet=True)
    assert entries[0]["check"] == "fail"
    assert entries[0]["exit_code"] == 1
    assert "vite failed" in entries[0]["stderr_tail"]


def test_extract_chunk_warnings_detects_vite_large_chunk_warning() -> None:
    output = "\n".join([
        "vite v5.0.0 building",
        "(!) Some chunks are larger than 500 kB after minification. Consider code-splitting.",
    ])

    warnings = module_sandbox_matrix.extract_chunk_warnings(output)

    assert len(warnings) == 1
    assert "Some chunks are larger" in warnings[0]


def test_check_records_frontend_chunk_warnings(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="(!) Some chunks are larger than 500 kB after minification.",
            stderr="",
        )

    monkeypatch.setattr(module_sandbox_matrix.subprocess, "run", fake_run)
    entries = [{
        "module": "front-only",
        "check": "pass",
        "backend_test_cmd": None,
        "frontend_build_cmd": "cd modules/front-only/sandbox && npm run build",
    }]

    assert module_sandbox_matrix.check_sandbox_matrix(entries, quiet=True)
    assert entries[0]["check"] == "pass"
    assert entries[0]["chunk_warnings"]


def test_frontend_install_needed_when_vite_bin_missing(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    package_json = sandbox / "package.json"
    package_json.write_text('{"scripts":{"build":"vite build"}}', encoding="utf-8")

    assert module_sandbox_matrix._frontend_install_needed(sandbox) is True

    vite_bin = sandbox / "node_modules" / ".bin" / "vite"
    vite_bin.parent.mkdir(parents=True)
    vite_bin.write_text("", encoding="utf-8")
    package_lock = sandbox / "node_modules" / ".package-lock.json"
    package_lock.write_text("{}", encoding="utf-8")
    assert module_sandbox_matrix._frontend_install_needed(sandbox) is False


def test_frontend_install_command_does_not_create_lock_when_missing(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    assert module_sandbox_matrix._frontend_install_command(sandbox) == [
        "npm",
        "install",
        "--package-lock=false",
        "--no-audit",
        "--no-fund",
    ]

    (sandbox / "package-lock.json").write_text("{}", encoding="utf-8")
    assert module_sandbox_matrix._frontend_install_command(sandbox) == [
        "npm",
        "ci",
        "--prefer-offline",
        "--no-audit",
        "--no-fund",
    ]


def test_sandbox_vite_modules_alias_points_to_modules_root() -> None:
    """Sandbox App.vue imports use @modules/<key>, so aliases must target modules/."""
    bad_configs = []
    for config in sorted((REPO_ROOT / "modules").glob("*/sandbox/vite.config.ts")):
        text = config.read_text(encoding="utf-8")
        if "path.resolve(__dirname, '..')" in text:
            bad_configs.append(str(config.relative_to(REPO_ROOT)))

    assert not bad_configs, "@modules alias points at module dir instead of modules root: " + ", ".join(bad_configs)


def test_sandbox_frontend_external_element_plus_imports_are_aliased() -> None:
    """Frontend files imported from outside sandbox need explicit dependency aliases."""
    missing_alias = []
    for module_dir in sorted((REPO_ROOT / "modules").iterdir()):
        if not module_dir.is_dir() or module_dir.name.startswith("_"):
            continue
        frontend_dir = module_dir / "frontend"
        config = module_dir / "sandbox" / "vite.config.ts"
        if not frontend_dir.exists() or not config.exists():
            continue
        imports_element_plus = any(
            "from 'element-plus'" in path.read_text(encoding="utf-8")
            or 'from "element-plus"' in path.read_text(encoding="utf-8")
            for path in frontend_dir.rglob("*")
            if path.suffix in {".vue", ".ts", ".tsx"}
        )
        if imports_element_plus and "'element-plus': path.resolve" not in config.read_text(encoding="utf-8"):
            missing_alias.append(module_dir.name)

    assert not missing_alias, "sandbox missing element-plus alias for external frontend imports: " + ", ".join(missing_alias)
