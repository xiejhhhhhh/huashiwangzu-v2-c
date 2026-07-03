"""FastAPI router for github-search module.

Cross-module capabilities:
  github-search:search      — Search GitHub repos with ranking
  github-search:search_code — Search code on GitHub
"""
import asyncio
import json
import logging
import os
import re as _re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.core.exceptions import AppException, RateLimitError, ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .services.github_client import (
    GitHubClientError,
    get_repo_readme,
    search_code,
    search_repositories,
)

logger = logging.getLogger("v2.github-search")

router = APIRouter(prefix="/api/github-search", tags=["github-search"])

_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_CALLS = 30
_RUNTIME_DIR_ENV = "GITHUB_SEARCH_RUNTIME_DIR"


@contextmanager
def _locked_file(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        handle.close()


def _runtime_dir() -> Path:
    configured = os.environ.get(_RUNTIME_DIR_ENV)
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "huashiwangzu_v2_github_search"


def _rate_limit_path() -> Path:
    return _runtime_dir() / "rate_limits.json"


def _load_rate_state(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring invalid github-search rate limit file: %s", exc)
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_rate_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(state, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _enforce_rate_limit(caller: str, action: str) -> None:
    path = _rate_limit_path()
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW_SECONDS
    state_key = f"{caller}:{action}"

    with _locked_file(path.with_suffix(".lock")):
        state = _load_rate_state(path)
        raw_timestamps = state.get(state_key, [])
        timestamps = [
            value for value in raw_timestamps
            if isinstance(value, (int, float)) and value >= window_start
        ]
        if len(timestamps) >= _RATE_LIMIT_MAX_CALLS:
            retry_after = max(1, int(timestamps[0] + _RATE_LIMIT_WINDOW_SECONDS - now))
            raise RateLimitError(
                f"github-search rate limit exceeded; retry after {retry_after}s",
            )
        timestamps.append(now)
        state[state_key] = timestamps
        _write_rate_state(path, state)


def _parse_limit(value: object, *, default: int = 5) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("limit must be an integer between 1 and 10")
    if value < 1 or value > 10:
        raise ValidationError("limit must be between 1 and 10")
    return value


def _normalize_language(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("language must be a string")
    normalized = value.strip()
    return normalized or None


def _raise_client_error(exc: GitHubClientError) -> None:
    if exc.code == "github_rate_limited":
        raise RateLimitError(str(exc)) from exc
    if exc.code == "github_query_invalid":
        raise ValidationError(str(exc)) from exc
    if exc.code in {"github_cli_missing", "github_auth_required"}:
        raise AppException(str(exc), code=exc.code.upper(), status_code=503) from exc
    if exc.code == "github_timeout":
        raise AppException(str(exc), code="GITHUB_TIMEOUT", status_code=504) from exc
    raise AppException(str(exc), code=exc.code.upper(), status_code=502) from exc


def _extract_owner_repo(url: str) -> tuple[str, str] | None:
    m = _re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if m:
        return m.group(1), m.group(2).rstrip("/")
    parts = url.strip("/").split("/")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None


def _format_repo_result(repo: dict[str, Any]) -> dict[str, Any]:
    owner, repo_name = _extract_owner_repo(repo.get("fullName", repo.get("url", ""))) or ("", "")
    license_info = repo.get("license")
    if isinstance(license_info, dict):
        license_str = license_info.get("spdx_id", license_info.get("key", ""))
    else:
        license_str = str(license_info or "")

    return {
        "name": repo.get("fullName", ""),
        "url": repo.get("url", f"https://github.com/{owner}/{repo_name}"),
        "description": repo.get("description", "") or "",
        "stars": repo.get("stargazersCount", 0),
        "language": repo.get("language") or "",
        "license": license_str,
        "last_updated": repo.get("pushedAt", ""),
        "open_issues": repo.get("openIssuesCount", 0),
    }


async def _cap_search(params: dict, caller: str) -> dict:
    """Search GitHub repositories with ranking."""
    query = (params.get("query") or "").strip()
    if not query:
        raise ValidationError("query is required")

    limit = _parse_limit(params.get("limit", 5))
    _enforce_rate_limit(caller, "search")
    try:
        repos = await search_repositories(query, limit)
    except GitHubClientError as exc:
        _raise_client_error(exc)

    results = [_format_repo_result(r) for r in repos]
    enriched = []
    for r in results:
        owner_repo = _extract_owner_repo(r["url"])
        if owner_repo:
            try:
                readme = await get_repo_readme(owner_repo[0], owner_repo[1])
            except GitHubClientError as exc:
                logger.info("Skipping README preview for %s: %s", r["url"], exc)
            else:
                if readme:
                    r["readme_preview"] = readme[:500]
        enriched.append(r)

    return {
        "results": enriched,
        "total": len(enriched),
        "query": query,
        "error": None,
    }


async def _cap_search_code(params: dict, caller: str) -> dict:
    """Search code on GitHub."""
    query = (params.get("query") or "").strip()
    if not query:
        raise ValidationError("query is required")

    language = _normalize_language(params.get("language"))
    limit = _parse_limit(params.get("limit", 5))
    _enforce_rate_limit(caller, "search_code")
    try:
        items = await search_code(query, language, limit)
    except GitHubClientError as exc:
        _raise_client_error(exc)

    results = []
    for item in items:
        repo = item.get("repository", {})
        repo_name = ""
        repo_url = ""
        if isinstance(repo, dict):
            repo_name = repo.get("nameWithOwner", "")
            repo_url = repo.get("url", "")
        results.append({
            "repository": repo_name,
            "url": repo_url,
            "file_path": item.get("path", ""),
            "snippets": [
                m.get("fragment", "")
                for m in (item.get("textMatches") or [])
            ],
        })

    return {"results": results, "total": len(results), "query": query, "error": None}


# ── HTTP endpoints for direct testing ──────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=10)


class SearchCodeRequest(BaseModel):
    query: str
    language: str | None = None
    limit: int = Field(default=5, ge=1, le=10)


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "github-search", "status": "ok"})


@router.post("/search")
async def http_search(
    body: SearchRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _cap_search(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/search-code")
async def http_search_code(
    body: SearchCodeRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _cap_search_code(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


# ── Register capabilities with framework ──────────────────────────────

register_capability(
    "github-search", "search", _cap_search,
    description="搜索 GitHub 开源项目，按活跃度和质量排序。输入关键词即可，无需 GitHub 搜索语法知识。自动过滤归档和不活跃（2年以上未更新）项目。返回结果含仓库名称、描述、Stars、语言、许可证、最后更新时间。",
    brief="搜索 GitHub 项目",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，如 'fastapi agent framework'",
            },
            "limit": {
                "type": "integer",
                "description": "返回结果数量（默认5，最大10）",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    min_role="viewer",
)

register_capability(
    "github-search", "search_code", _cap_search_code,
    description="在 GitHub 上搜索代码片段。返回包含匹配代码的文件路径、仓库信息和代码片段预览。支持按编程语言过滤。",
    brief="搜索 GitHub 代码",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "代码搜索关键词，如 'register_capability'",
            },
            "language": {
                "type": "string",
                "description": "编程语言过滤（可选），如 python、javascript、go",
            },
            "limit": {
                "type": "integer",
                "description": "返回结果数量（默认5，最大10）",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    min_role="viewer",
)

# ── Startup health check ──────────────────────────────────────────────
@router.on_event("startup")
async def _verify_gh_cli():
    try:
        result = await asyncio.create_subprocess_exec(
            "gh", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await result.communicate()
    except FileNotFoundError:
        logger.warning("gh CLI not found — github-search module will be unavailable")
        return
    if result.returncode == 0:
        logger.info("gh CLI verified: %s", stdout.decode().strip())
    else:
        logger.warning("gh CLI not found — github-search module will be unavailable")
