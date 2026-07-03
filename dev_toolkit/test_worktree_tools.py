"""Tests for worktree boundary matching helpers."""

import json
from pathlib import Path

import anyio

from dev_toolkit.worktree_tools import path_matches_forbidden, path_matches_prefix, worktree_guard


def test_path_matches_prefix_only_matches_rooted_prefix() -> None:
    assert path_matches_prefix("modules/knowledge/router.py", "modules/knowledge")
    assert not path_matches_prefix("modules/foo/backend/file.py", "backend")


def test_path_matches_forbidden_matches_nested_directory_names() -> None:
    assert path_matches_forbidden("modules/foo/__pycache__/x.pyc", "__pycache__")
    assert path_matches_forbidden("__pycache__/x.pyc", "__pycache__")
    assert not path_matches_forbidden("modules/foo/cache.py", "__pycache__")


def test_path_matches_forbidden_keeps_path_prefixes_strict() -> None:
    assert path_matches_forbidden("backend/.venv/lib/site.py", "backend/.venv")
    assert not path_matches_forbidden("modules/foo/backend/.venv/site.py", "backend/.venv")


def _run_guard(status_lines: list[str], **kwargs: str) -> dict:
    async def fake_run_command_json(*_args, **_kwargs) -> dict:
        return {"stdout": "\n".join(status_lines), "success": True, "returncode": 0}

    async def run() -> dict:
        raw = await worktree_guard(fake_run_command_json, Path("/repo"), **kwargs)
        data = json.loads(raw)
        assert isinstance(data, dict)
        return data

    return anyio.run(run)


def test_worktree_guard_without_baseline_keeps_old_boundary_failure() -> None:
    data = _run_guard(
        ["?? modules/knowledge/backend/router.py"],
        allowed_prefixes="dev_toolkit",
    )

    assert data["success"] is False
    assert data["outside_allowed"] == ["modules/knowledge/backend/router.py"]
    assert data["new_outside_allowed"] == ["modules/knowledge/backend/router.py"]
    assert data["baseline_count"] == 0


def test_worktree_guard_baseline_existing_outside_change_does_not_fail() -> None:
    data = _run_guard(
        ["?? modules/knowledge/backend/router.py"],
        allowed_prefixes="dev_toolkit",
        baseline_paths="modules/knowledge/backend/router.py",
    )

    assert data["success"] is True
    assert data["outside_allowed"] == ["modules/knowledge/backend/router.py"]
    assert data["new_outside_allowed"] == []
    assert data["acknowledged_outside_changes"] == ["modules/knowledge/backend/router.py"]


def test_worktree_guard_new_outside_change_after_baseline_fails() -> None:
    data = _run_guard(
        [
            "?? modules/knowledge/backend/router.py",
            "?? backend/app/routers/files.py",
        ],
        allowed_prefixes="dev_toolkit",
        baseline_paths="modules/knowledge/backend/router.py",
    )

    assert data["success"] is False
    assert data["new_outside_allowed"] == ["backend/app/routers/files.py"]
    assert data["acknowledged_outside_changes"] == ["modules/knowledge/backend/router.py"]


def test_worktree_guard_allowed_prefixes_baseline_and_memory_pass() -> None:
    baseline_status = json.dumps({"changed_files": ["modules/knowledge/backend/router.py"]})
    data = _run_guard(
        [
            "?? modules/knowledge/backend/router.py",
            " M dev_toolkit/worktree_tools.py",
            "?? 开发文档/项目记忆/r5-mcp-baseline.md",
        ],
        allowed_prefixes="dev_toolkit\n开发文档/项目记忆",
        baseline_status_json=baseline_status,
    )

    assert data["success"] is True
    assert data["new_since_baseline"] == [
        "dev_toolkit/worktree_tools.py",
        "开发文档/项目记忆/r5-mcp-baseline.md",
    ]
    assert data["new_outside_allowed"] == []
    assert data["acknowledged_outside_changes"] == ["modules/knowledge/backend/router.py"]
