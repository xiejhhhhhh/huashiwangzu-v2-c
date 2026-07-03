"""Offline sandbox tests for the github-search module.

The tests stub GitHub CLI calls and use a temporary runtime directory, so no
real GitHub requests are made and no cache/rate-limit test data is left behind.
"""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_ROOT = PROJECT_ROOT / "modules" / "github-search"
CLIENT_PATH = MODULE_ROOT / "backend" / "services" / "github_client.py"
ROUTER_PATH = MODULE_ROOT / "backend" / "router.py"
MANIFEST_PATH = MODULE_ROOT / "manifest.json"
RUNTIME_ENV = "GITHUB_SEARCH_RUNTIME_DIR"


def _load_client(runtime_dir: str) -> types.ModuleType:
    os.environ[RUNTIME_ENV] = runtime_dir
    spec = importlib.util.spec_from_file_location(
        "github_search_client_sandbox",
        CLIENT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {CLIENT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_router(runtime_dir: str) -> types.ModuleType:
    os.environ[RUNTIME_ENV] = runtime_dir
    os.environ.setdefault("JWT_SECRET", "github-search-sandbox-secret")
    backend_path = str(PROJECT_ROOT / "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    package_name = "github_search_backend_sandbox"
    package = types.ModuleType(package_name)
    package.__path__ = [str(MODULE_ROOT / "backend")]
    sys.modules[package_name] = package

    spec = importlib.util.spec_from_file_location(
        f"{package_name}.router",
        ROUTER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {ROUTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{package_name}.router"] = module
    spec.loader.exec_module(module)
    return module


def _with_client() -> tuple[types.ModuleType, tempfile.TemporaryDirectory[str], str | None]:
    previous_runtime = os.environ.get(RUNTIME_ENV)
    runtime_dir = tempfile.TemporaryDirectory()
    client = _load_client(runtime_dir.name)
    client.clear_cache()
    return client, runtime_dir, previous_runtime


def _with_router() -> tuple[types.ModuleType, tempfile.TemporaryDirectory[str], str | None]:
    previous_runtime = os.environ.get(RUNTIME_ENV)
    runtime_dir = tempfile.TemporaryDirectory()
    router = _load_router(runtime_dir.name)
    return router, runtime_dir, previous_runtime


def _restore_runtime(runtime_dir: tempfile.TemporaryDirectory[str], previous_runtime: str | None) -> None:
    runtime_dir.cleanup()
    if previous_runtime is None:
        os.environ.pop(RUNTIME_ENV, None)
    else:
        os.environ[RUNTIME_ENV] = previous_runtime


def _repo_fixture() -> dict[str, Any]:
    return {
        "fullName": "tiangolo/fastapi",
        "description": "FastAPI framework",
        "stargazersCount": 80000,
        "forksCount": 7000,
        "pushedAt": datetime.now(timezone.utc).isoformat(),
        "url": "https://github.com/tiangolo/fastapi",
        "isArchived": False,
        "isFork": False,
        "isDisabled": False,
        "language": "Python",
        "license": {"spdx_id": "MIT"},
        "openIssuesCount": 100,
        "createdAt": "2018-12-01T00:00:00Z",
    }


def _assert_non_empty_string(value: Any, name: str) -> None:
    assert isinstance(value, str) and value.strip(), (
        f"{name} is required and must be a non-empty string"
    )


def _validate_limit(value: Any, *, default: int = 5, maximum: int = 10) -> int:
    if value is None:
        return default
    assert isinstance(value, int) and not isinstance(value, bool), (
        f"limit must be an integer, got: {type(value).__name__}"
    )
    assert 1 <= value <= maximum, f"limit must be between 1 and {maximum}, got: {value}"
    return value


def _assert_raises_assertion(callback: Any) -> None:
    try:
        callback()
    except AssertionError:
        return
    raise AssertionError("Expected validation assertion")


def test_manifest_public_actions_match_backend_contract() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    actions = {item["action"]: item for item in manifest["public_actions"]}

    assert set(actions) == {"search", "search_code"}
    assert set(actions["search"]["parameters"]) == {"query", "limit"}
    assert set(actions["search_code"]["parameters"]) == {"query", "language", "limit"}
    assert actions["search"]["min_role"] == "viewer"
    assert actions["search_code"]["min_role"] == "viewer"


def test_parameter_validation_contract() -> None:
    _assert_non_empty_string("language:python stars:>100", "query")
    assert _validate_limit(None) == 5
    assert _validate_limit(1) == 1
    assert _validate_limit(10) == 10

    for invalid_limit in (0, 11, "10", True):
        _assert_raises_assertion(lambda value=invalid_limit: _validate_limit(value))

    for invalid_query in ("", "   "):
        _assert_raises_assertion(lambda value=invalid_query: _assert_non_empty_string(value, "query"))


def test_repository_search_distinguishes_empty_from_failure() -> None:
    client, runtime_dir, previous_runtime = _with_client()
    try:
        async def empty_search(args: list[str]) -> str:
            assert args[:2] == ["search", "repos"]
            return "[]"

        client._run_gh = empty_search
        assert asyncio.run(client.search_repositories("nothing-here", 5)) == []

        async def failed_search(args: list[str]) -> str:
            raise client.GitHubClientError("rate limit exceeded", code="github_rate_limited")

        client.clear_cache()
        client._run_gh = failed_search
        try:
            asyncio.run(client.search_repositories("fastapi", 5))
            raise AssertionError("Search failure should raise GitHubClientError")
        except client.GitHubClientError as exc:
            assert exc.code == "github_rate_limited"
    finally:
        _restore_runtime(runtime_dir, previous_runtime)


def test_successful_repository_results_are_cached() -> None:
    client, runtime_dir, previous_runtime = _with_client()
    calls = {"count": 0}
    try:
        async def repo_search(args: list[str]) -> str:
            calls["count"] += 1
            return json.dumps([_repo_fixture()])

        client._run_gh = repo_search
        first = asyncio.run(client.search_repositories("fastapi", 3))
        second = asyncio.run(client.search_repositories("fastapi", 3))

        assert calls["count"] == 1
        assert first == second
        assert first[0]["fullName"] == "tiangolo/fastapi"
    finally:
        _restore_runtime(runtime_dir, previous_runtime)


def test_code_search_accepts_empty_results_and_caches_success() -> None:
    client, runtime_dir, previous_runtime = _with_client()
    calls = {"count": 0}
    try:
        async def code_search(args: list[str]) -> str:
            calls["count"] += 1
            assert "--language" in args
            return json.dumps([
                {
                    "repository": {
                        "nameWithOwner": "openai/openai-python",
                        "url": "https://github.com/openai/openai-python",
                    },
                    "path": "src/openai/__init__.py",
                    "textMatches": [{"fragment": "from openai import OpenAI"}],
                    "url": "https://github.com/openai/openai-python/blob/main/src/openai/__init__.py",
                },
            ])

        client._run_gh = code_search
        first = asyncio.run(client.search_code("OpenAI", "python", 2))
        second = asyncio.run(client.search_code("OpenAI", "python", 2))

        assert calls["count"] == 1
        assert first == second
        assert first[0]["repository"]["nameWithOwner"] == "openai/openai-python"
    finally:
        _restore_runtime(runtime_dir, previous_runtime)


def test_router_error_semantics_use_exceptions_not_data_errors() -> None:
    router, runtime_dir, previous_runtime = _with_router()
    try:
        async def empty_repositories(query: str, limit: int) -> list[dict[str, Any]]:
            assert query == "definitely-empty"
            assert limit == 1
            return []

        async def no_readme(owner: str, repo: str) -> None:
            return None

        router.search_repositories = empty_repositories
        router.get_repo_readme = no_readme

        empty_result = asyncio.run(
            router._cap_search({"query": "definitely-empty", "limit": 1}, "user:1"),
        )
        assert empty_result == {
            "results": [],
            "total": 0,
            "query": "definitely-empty",
            "error": None,
        }

        for invalid_params in ({"query": "   ", "limit": 1}, {"query": "ok", "limit": 0}):
            try:
                asyncio.run(router._cap_search(invalid_params, "user:1"))
                raise AssertionError("Invalid params should raise ValidationError")
            except router.ValidationError:
                pass

        async def limited_repositories(query: str, limit: int) -> list[dict[str, Any]]:
            raise router.GitHubClientError("rate limit exceeded", code="github_rate_limited")

        router.search_repositories = limited_repositories
        try:
            asyncio.run(router._cap_search({"query": "fastapi", "limit": 1}, "user:1"))
            raise AssertionError("GitHub rate limits should raise RateLimitError")
        except router.RateLimitError:
            pass
    finally:
        _restore_runtime(runtime_dir, previous_runtime)


def test_search_output_contract_shape() -> None:
    repo_result_keys = {
        "name",
        "url",
        "description",
        "stars",
        "language",
        "license",
        "last_updated",
        "open_issues",
    }
    code_result_keys = {"repository", "url", "file_path", "snippets"}

    assert repo_result_keys == {
        "name",
        "url",
        "description",
        "stars",
        "language",
        "license",
        "last_updated",
        "open_issues",
    }
    assert code_result_keys == {"repository", "url", "file_path", "snippets"}


def main() -> None:
    tests = [
        test_manifest_public_actions_match_backend_contract,
        test_parameter_validation_contract,
        test_repository_search_distinguishes_empty_from_failure,
        test_successful_repository_results_are_cached,
        test_code_search_accepts_empty_results_and_caches_success,
        test_router_error_semantics_use_exceptions_not_data_errors,
        test_search_output_contract_shape,
    ]
    print("=" * 60)
    print("github-search sandbox test")
    print("=" * 60)
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print("=" * 60)
    print("PASS: github-search sandbox test")


if __name__ == "__main__":
    main()
