"""GitHub CLI wrapper for searching repositories and code.

Uses `gh` CLI (must be installed and authenticated).
Results are structured for consumption by AI agents.
"""
import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("v2.github-search").getChild("client")

_GH_TIMEOUT = 15
_MAX_SEARCH_RESULTS = 10
_CACHE_TTL = timedelta(minutes=10)
_RUNTIME_DIR_ENV = "GITHUB_SEARCH_RUNTIME_DIR"

_REPO_FIELDS = [
    "fullName", "description", "stargazersCount", "forksCount",
    "pushedAt", "url", "isArchived", "isFork", "isDisabled",
    "language", "license", "openIssuesCount", "createdAt",
]

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
CacheValue = list[dict[str, Any]] | str

_memory_cache: dict[str, tuple[datetime, CacheValue]] = {}


class GitHubClientError(RuntimeError):
    """Raised when GitHub CLI execution or parsing fails."""

    def __init__(self, message: str, *, code: str = "github_cli_error") -> None:
        self.code = code
        super().__init__(message)


def _gh_path() -> str:
    """Return gh binary path. Prefer locally installed, fallback to PATH."""
    return os.environ.get("GH_PATH") or "gh"


def _runtime_dir() -> Path:
    configured = os.environ.get(_RUNTIME_DIR_ENV)
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "huashiwangzu_v2_github_search"


def _cache_path() -> Path:
    return _runtime_dir() / "cache.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _classify_cli_error(stderr: str) -> tuple[str, str]:
    message = stderr.strip() or "GitHub CLI request failed"
    lower = message.lower()
    if "rate limit" in lower:
        return "github_rate_limited", message
    if "not logged into" in lower or "requires authentication" in lower or "authentication" in lower:
        return "github_auth_required", message
    if "invalid search query" in lower or "validation failed" in lower:
        return "github_query_invalid", message
    return "github_cli_error", message


def _load_disk_cache() -> dict[str, Any]:
    path = _cache_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring invalid github-search cache file: %s", exc)
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_disk_cache(data: dict[str, Any]) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _get_cached(cache_key: str) -> CacheValue | None:
    now = _utc_now()
    cached = _memory_cache.get(cache_key)
    if cached and now < cached[0]:
        logger.debug("Memory cache hit: %s", cache_key)
        return cached[1]

    disk_cache = _load_disk_cache()
    item = disk_cache.get(cache_key)
    if not isinstance(item, dict):
        return None

    expires_at_raw = item.get("expires_at")
    value = item.get("value")
    if not isinstance(expires_at_raw, str):
        return None
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except ValueError:
        return None
    if now >= expires_at:
        return None
    if not isinstance(value, (list, str)):
        return None

    _memory_cache[cache_key] = (expires_at, value)
    logger.debug("Disk cache hit: %s", cache_key)
    return value


def _set_cached(cache_key: str, value: CacheValue) -> None:
    expires_at = _utc_now() + _CACHE_TTL
    _memory_cache[cache_key] = (expires_at, value)

    disk_cache = _load_disk_cache()
    now = _utc_now()
    fresh_cache: dict[str, JsonValue] = {}
    for key, item in disk_cache.items():
        if not isinstance(item, dict):
            continue
        expires_at_raw = item.get("expires_at")
        if not isinstance(expires_at_raw, str):
            continue
        try:
            item_expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            continue
        if now < item_expires_at:
            fresh_cache[key] = item

    fresh_cache[cache_key] = {
        "expires_at": expires_at.isoformat(),
        "value": value,
    }
    _write_disk_cache(fresh_cache)


async def _run_gh(args: list[str]) -> str:
    """Run gh CLI with timeout. Returns stdout on success or raises."""
    cmd = [_gh_path()] + args
    logger.debug("Running: %s", " ".join(cmd))
    try:
        proc = await asyncio.create_subprocess_exec(
            cmd[0], *cmd[1:],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_GH_TIMEOUT)
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.warning("gh CLI error (code=%d): %s", proc.returncode, err)
            code, message = _classify_cli_error(err)
            raise GitHubClientError(message, code=code)
        return stdout.decode()
    except asyncio.TimeoutError:
        logger.warning("gh CLI timed out (%ds): %s", _GH_TIMEOUT, " ".join(args))
        raise GitHubClientError("GitHub CLI request timed out", code="github_timeout") from None
    except FileNotFoundError:
        logger.error("gh CLI not found. Install GitHub CLI: https://cli.github.com")
        raise GitHubClientError("GitHub CLI is not installed", code="github_cli_missing") from None
    except Exception as exc:
        if isinstance(exc, GitHubClientError):
            raise
        logger.error("gh CLI error: %s", exc)
        raise GitHubClientError("GitHub CLI request failed", code="github_cli_error") from exc


def _is_active(repo: dict[str, Any]) -> bool:
    """Filter out archived, disabled, and long-dormant repos."""
    if repo.get("isArchived") or repo.get("isDisabled"):
        return False
    pushed = repo.get("pushedAt")
    if not pushed:
        return False
    try:
        pushed_dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return True
    age = datetime.now(timezone.utc) - pushed_dt
    if age > timedelta(days=365 * 2):
        return False
    return True


async def search_repositories(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search GitHub repositories by keyword. Returns ranked, filtered results."""
    cache_key = f"repos:{query}:{limit}"
    cached = _get_cached(cache_key)
    if isinstance(cached, list):
        return cached

    limit = max(1, min(limit, _MAX_SEARCH_RESULTS))
    fields = ",".join(_REPO_FIELDS)
    raw = await _run_gh([
        "search", "repos", query,
        "--sort", "stars",
        "--order", "desc",
        "--limit", str(limit * 2),
        "--json", fields,
    ])

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error: %s", exc)
        raise GitHubClientError("GitHub CLI returned invalid JSON", code="github_json_invalid") from exc
    if not isinstance(parsed, list):
        raise GitHubClientError("GitHub CLI returned an unexpected repository payload", code="github_json_invalid")

    repos = [r for r in parsed if isinstance(r, dict) and _is_active(r)]
    repos = repos[:limit]
    _set_cached(cache_key, repos)
    return repos


async def search_code(query: str, language: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Search code on GitHub."""
    cache_key = f"code:{query}:{language}:{limit}"
    cached = _get_cached(cache_key)
    if isinstance(cached, list):
        return cached

    limit = max(1, min(limit, _MAX_SEARCH_RESULTS))
    args = ["search", "code", query, "--limit", str(limit), "--json", "repository,path,textMatches,url"]
    if language:
        args += ["--language", language]

    raw = await _run_gh(args)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error: %s", exc)
        raise GitHubClientError("GitHub CLI returned invalid JSON", code="github_json_invalid") from exc
    if not isinstance(parsed, list):
        raise GitHubClientError("GitHub CLI returned an unexpected code-search payload", code="github_json_invalid")

    results = [item for item in parsed if isinstance(item, dict)]
    _set_cached(cache_key, results)
    return results


async def get_repo_readme(owner: str, repo: str) -> str | None:
    """Fetch README of a repository (text output, first 2000 chars)."""
    cache_key = f"readme:{owner}/{repo}"
    cached = _get_cached(cache_key)
    if isinstance(cached, str):
        return cached

    raw = await _run_gh([
        "repo", "view", f"{owner}/{repo}",
    ])

    try:
        lines = raw.split("\n", 1)
        if len(lines) > 1:
            readme = lines[1].strip()
        else:
            readme = lines[0].strip()
        preview = readme[:2000]
        _set_cached(cache_key, preview)
        return preview
    except Exception as exc:
        logger.warning("Failed to parse repo view for %s/%s: %s", owner, repo, exc)
        return None


def clear_cache() -> None:
    _memory_cache.clear()
    try:
        _cache_path().unlink()
    except FileNotFoundError:
        pass
    logger.info("Cache cleared")
