import json
import sys
from pathlib import Path

import anyio
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("mcp")

from dev_toolkit import code_tools, core_tools, server  # noqa: E402


def test_project_python_prefers_backend_venv() -> None:
    expected = server.REPO_ROOT / "backend" / ".venv" / "bin" / "python"
    if expected.exists():
        assert server._project_python() == str(expected)
    else:
        assert server._project_python() == sys.executable


@pytest.mark.parametrize(
    "query",
    [
        "select 1",
        "WITH rows AS (SELECT 1 AS id) SELECT * FROM rows",
        "EXPLAIN (FORMAT JSON) SELECT * FROM framework_file_items",
        "SHOW max_connections",
        "VALUES (1), (2)",
        "SELECT '; drop table x' AS literal",
        "SELECT '-- not a comment' AS literal",
    ],
)
def test_check_sql_readonly_allows_safe_read_queries(query: str) -> None:
    server._check_sql_readonly(query)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT 1; SELECT 2",
        "SELECT 1; DROP TABLE framework_file_items",
        "SELECT 1 -- hide the rest\n",
        "SELECT /* hide */ 1",
        "WITH deleted AS (DELETE FROM framework_file_items RETURNING *) SELECT * FROM deleted",
        "EXPLAIN UPDATE framework_file_items SET name = 'x'",
        "EXPLAIN (FORMAT JSON) CREATE TABLE audit_tmp(id int)",
        "INSERT INTO audit_tmp VALUES (1)",
        "SELECT * INTO audit_tmp FROM framework_file_items",
        "DO $$ BEGIN DELETE FROM framework_file_items; END $$",
        "SELECT 'unterminated",
    ],
)
def test_check_sql_readonly_rejects_writes_chains_and_comment_bypass(query: str) -> None:
    with pytest.raises(ValueError):
        server._check_sql_readonly(query)


def test_extract_prefixed_json_reads_machine_verdict_from_tail() -> None:
    output = 'human\nSMOKE_JSON: {"verdict": "PASS_WITH_DEBT", "counts": {"skipped": 1}}\n'
    assert server._extract_prefixed_json(output, "SMOKE_JSON:") == {
        "verdict": "PASS_WITH_DEBT",
        "counts": {"skipped": 1},
    }


def test_release_gate_response_does_not_map_debt_to_clean_success() -> None:
    output = 'human\nRELEASE_GATE_JSON: {"verdict": "PASS_WITH_DEBT", "has_debt": true}\n'
    result = server._build_release_gate_response(
        output=output,
        returncode=0,
        skip_ui=True,
        duration_seconds=1.2345,
    )

    assert result["success"] is False
    assert result["clean_pass"] is False
    assert result["release_safe"] is True
    assert result["has_debt"] is True
    assert result["verdict"] == "PASS_WITH_DEBT"


def test_normalize_pytest_targets_accepts_backend_prefixed_path() -> None:
    target = "backend/tests/test_agent_inline_tool_calls.py::TestFinalCleanContent"
    normalized = server._normalize_pytest_targets(target)
    assert normalized == ["tests/test_agent_inline_tool_calls.py::TestFinalCleanContent"]


def test_normalize_pytest_targets_accepts_repo_relative_path() -> None:
    target = "tests/test_agent_inline_tool_calls.py"
    normalized = server._normalize_pytest_targets(target)
    assert normalized == ["tests/test_agent_inline_tool_calls.py"]


def test_normalize_pytest_targets_accepts_dev_toolkit_repo_path() -> None:
    target = "dev_toolkit/test_server_helpers.py"
    normalized = server._normalize_pytest_targets(target)
    assert normalized == [str(server.REPO_ROOT / target)]


def test_normalize_pytest_targets_accepts_backend_prefixed_dev_toolkit_path() -> None:
    target = "backend/dev_toolkit/test_server_helpers.py::test_tail_text_keeps_short_output"
    normalized = server._normalize_pytest_targets(target)
    assert normalized == [
        str(server.REPO_ROOT / "dev_toolkit/test_server_helpers.py") + "::test_tail_text_keeps_short_output"
    ]


def test_run_test_uses_repo_root_for_dev_toolkit_targets() -> None:
    calls = []

    async def fake_run_command_json(cmd, *, cwd: Path, timeout: int = 120):
        calls.append({"cmd": cmd, "cwd": cwd, "timeout": timeout})
        return {"success": True, "returncode": 0, "stdout": "ok", "stderr": ""}

    async def run() -> None:
        await code_tools.run_test(fake_run_command_json, server.REPO_ROOT, "dev_toolkit/test_server_helpers.py")

    anyio.run(run)

    assert calls
    assert calls[0]["cwd"] == server.REPO_ROOT
    assert calls[0]["cmd"][0] == "env"
    assert str(server.REPO_ROOT) in calls[0]["cmd"][1]


def test_run_test_uses_absolute_backend_target_when_mixed_with_repo_target() -> None:
    calls = []

    async def fake_run_command_json(cmd, *, cwd: Path, timeout: int = 120):
        calls.append({"cmd": cmd, "cwd": cwd, "timeout": timeout})
        return {"success": True, "returncode": 0, "stdout": "ok", "stderr": ""}

    async def run() -> None:
        await code_tools.run_test(
            fake_run_command_json,
            server.REPO_ROOT,
            "backend/tests/test_agent_inline_tool_calls.py dev_toolkit/test_server_helpers.py",
        )

    anyio.run(run)

    assert calls
    assert calls[0]["cwd"] == server.REPO_ROOT
    assert str(server.REPO_ROOT / "backend/tests/test_agent_inline_tool_calls.py") in calls[0]["cmd"]
    assert str(server.REPO_ROOT / "dev_toolkit/test_server_helpers.py") in calls[0]["cmd"]


def test_lint_accepts_comma_and_newline_separated_paths() -> None:
    calls = []

    async def fake_run_command_json(cmd, *, cwd: Path, timeout: int = 120):
        calls.append({"cmd": cmd, "cwd": cwd, "timeout": timeout})
        return {"success": True, "returncode": 0, "stdout": "", "stderr": "", "duration_seconds": 0.01}

    async def run() -> dict:
        raw = await code_tools.lint(
            fake_run_command_json,
            server.REPO_ROOT,
            "ruff",
            "dev_toolkit/code_tools.py,\ndev_toolkit/agent_board_tools.py",
        )
        data = json.loads(raw)
        assert isinstance(data, dict)
        return data

    data = anyio.run(run)

    assert data["success"] is True
    assert data["failed_count"] == 0
    assert data["paths"] == ["dev_toolkit/code_tools.py", "dev_toolkit/agent_board_tools.py"]
    assert len(calls) == 2
    assert calls[0]["cmd"][-1].endswith("dev_toolkit/code_tools.py")
    assert calls[1]["cmd"][-1].endswith("dev_toolkit/agent_board_tools.py")


def test_finish_task_forwards_allowed_prefixes_to_worktree_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    async def fake_git_status_summary(*_args, **_kwargs) -> dict:
        return {"branch": "codex/test", "is_main": False, "dirty_count": 0, "sample": []}

    async def fake_worktree_guard(
        _run_command_json,
        _repo_root,
        *,
        module_key: str = "",
        allowed_prefixes: str = "",
        forbidden_prefixes: str = "",
        include_untracked: bool = True,
        baseline_paths: str = "",
        baseline_status_json: str = "",
    ) -> str:
        calls.append({
            "module_key": module_key,
            "allowed_prefixes": allowed_prefixes,
            "forbidden_prefixes": forbidden_prefixes,
            "include_untracked": include_untracked,
            "baseline_paths": baseline_paths,
            "baseline_status_json": baseline_status_json,
        })
        return json.dumps({"success": True, "outside_allowed": []})

    monkeypatch.setattr(server, "git_status_summary", fake_git_status_summary)
    monkeypatch.setattr(server, "worktree_guard", fake_worktree_guard)

    async def run() -> dict:
        raw = await server._finish_task(
            "finish with memory",
            module_key="knowledge",
            allowed_prefixes="modules/knowledge\n开发文档/项目记忆",
            baseline_paths="backend/app/preexisting.py",
            baseline_status_json='{"changed_files":["modules/other/preexisting.py"]}',
        )
        return json.loads(raw)

    data = anyio.run(run)

    assert data["success"] is True
    assert calls == [{
        "module_key": "knowledge",
        "allowed_prefixes": "modules/knowledge\n开发文档/项目记忆",
        "forbidden_prefixes": "",
        "include_untracked": True,
        "baseline_paths": "backend/app/preexisting.py",
        "baseline_status_json": '{"changed_files":["modules/other/preexisting.py"]}',
    }]


def test_finish_task_schema_exposes_baseline_parameters() -> None:
    finish_tool = next(tool for tool in core_tools.tool_definitions() if tool.name == "finish_task")
    properties = finish_tool.inputSchema["properties"]

    assert "baseline_paths" in properties
    assert "baseline_status_json" in properties


def test_normalize_pytest_targets_accepts_module_repo_path() -> None:
    target = "modules/agent/backend/engine/test_fallback_chain.py"
    normalized = server._normalize_pytest_targets(target)
    assert normalized == [str(server.REPO_ROOT / target)]


def test_normalize_pytest_targets_accepts_absolute_backend_path() -> None:
    target_path = server.REPO_ROOT / "backend" / "tests" / "test_agent_inline_tool_calls.py"
    normalized = server._normalize_pytest_targets(str(target_path))
    assert normalized == ["tests/test_agent_inline_tool_calls.py"]


def test_resolve_repo_path_rejects_outside_repo(tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="路径必须在仓库内"):
        server._resolve_repo_path(str(outside))


def test_tail_text_keeps_short_output() -> None:
    assert server._tail_text("abc", limit=10) == "abc"


def test_tail_text_truncates_from_end() -> None:
    assert server._tail_text("abcdef", limit=3) == "def"


def test_clear_log_keeps_state_files_and_clears_selected_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)
    monkeypatch.setattr(server, "_LOG_MAP", {"backend": "backend.log", "agent": "modules/agent.log"})

    backend_log = tmp_path / "backend.log"
    agent_log = tmp_path / "modules" / "agent.log"
    port_file = tmp_path / ".backend.port"
    pid_file = tmp_path / ".watchdog.pid"

    backend_log.parent.mkdir(parents=True, exist_ok=True)
    agent_log.parent.mkdir(parents=True, exist_ok=True)
    backend_log.write_text("one\ntwo\n", encoding="utf-8")
    agent_log.write_text("alpha\nbeta\n", encoding="utf-8")
    port_file.write_text("33000\n", encoding="utf-8")
    pid_file.write_text("12345\n", encoding="utf-8")

    result = server._clear_log(module="backend", all_logs=False, keep_state=True)

    assert result["success"] is True
    assert backend_log.read_text(encoding="utf-8") == ""
    assert agent_log.read_text(encoding="utf-8") == "alpha\nbeta\n"
    assert port_file.read_text(encoding="utf-8") == "33000\n"
    assert pid_file.read_text(encoding="utf-8") == "12345\n"
    assert "backend.log" in result["cleared"][0]
    assert result["preserved"] == [".backend.port", ".watchdog.pid"]


def test_clear_log_all_logs_truncates_every_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)

    first_log = tmp_path / "uvicorn.out"
    second_log = tmp_path / "modules" / "agent.log"
    second_log.parent.mkdir(parents=True, exist_ok=True)
    first_log.write_text("hello\n", encoding="utf-8")
    second_log.write_text("world\n", encoding="utf-8")

    result = server._clear_log(module="backend", all_logs=True, keep_state=False)

    assert result["success"] is True
    assert first_log.read_text(encoding="utf-8") == ""
    assert second_log.read_text(encoding="utf-8") == ""
    assert result["preserved"] == []
