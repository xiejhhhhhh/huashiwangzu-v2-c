"""Workspace isolation, dangerous command detection, sandbox profile, safe env.

Shared by all terminal-tools capabilities.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from app.core.command_safety import check_dangerous_command as _check_dangerous_command
from app.core.workspace_security import (
    ensure_user_workspace as _user_workspace,
)
from app.core.workspace_security import (
    resolve_workspace_path as _resolve_workspace_path,
)
from app.services.file_reader import resolve_caller_user_id

logger = logging.getLogger("v2.terminal-tools")

__all__ = [
    "_DEFAULT_TIMEOUT",
    "_MAX_FILE_READ_BYTES",
    "_MAX_LIST_ITEMS",
    "_MAX_OUTPUT_BYTES",
    "_build_sandbox_profile",
    "_check_dangerous_command",
    "_check_path_escape",
    "_coerce_timeout",
    "_resolve_user_id",
    "_resolve_workspace_path",
    "_run_process_capped",
    "_safe_env",
    "_safe_external_filename",
    "_user_workspace",
    "_workspace_boundary_error",
    "_workspace_relative_path",
]

_MAX_OUTPUT_BYTES = 1 * 1024 * 1024   # 1 MB
_MAX_FILE_READ_BYTES = 1 * 1024 * 1024  # 1 MB
_MAX_LIST_ITEMS = 1000
_DEFAULT_TIMEOUT = 60                  # seconds


def _resolve_user_id(caller: str) -> int:
    """Compatibility wrapper for older handlers."""
    return resolve_caller_user_id(caller)


def _coerce_timeout(value: object, default: int = _DEFAULT_TIMEOUT, maximum: int = 600) -> int:
    """Parse timeout defensively for capability calls that bypass Pydantic."""
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return default
    if timeout <= 0 or timeout > maximum:
        return default
    return timeout


def _check_path_escape(command: str, workspace_real: str) -> str | None:
    """Check if command tries to access filesystem paths outside the workspace."""
    import shlex

    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None

    if not tokens:
        return None

    TRAVERSAL_CMDS = frozenset({
        'cd', 'ls', 'find', 'tree', 'cat', 'less', 'more',
        'head', 'tail', 'nl', 'wc', 'stat', 'du', 'file',
        'readlink', 'realpath', 'dirname', 'cp', 'mv', 'touch',
        'mkdir', 'rmdir', 'rm', 'tee',
    })
    SEPARATORS = {'&&', '||', ';', '|'}

    cmd_name = ""

    for token in tokens:
        if token in SEPARATORS:
            cmd_name = ""
            continue
        if not cmd_name:
            cmd_name = token
            continue
        if cmd_name not in TRAVERSAL_CMDS:
            continue
        if token.startswith('-') or token in {'>', '>>', '<'}:
            continue
        if token == '~' or token.startswith('~/'):
            return (f"Path escape blocked: '{token}' expands to"
                    " home directory outside workspace")
        try:
            resolved = os.path.realpath(os.path.join(workspace_real, token))
        except (OSError, ValueError):
            continue

        resolved_str = str(resolved)
        ws_prefix = workspace_real.rstrip('/') + '/'
        if not resolved_str.startswith(ws_prefix) and resolved_str != workspace_real:
            return (f"Path escape blocked: '{token}' resolves to"
                    " a location outside workspace")

    return None


# ── macOS sandbox-exec profile ────────────────────────────────────────

_PY_PREFIX = os.path.realpath(sys.prefix)
_PY_BASE_PREFIX = os.path.realpath(sys.base_prefix)


def _build_sandbox_profile(workspace_real: str) -> str:
    """Return a sandbox-exec profile string that locks the child process to
    read-only system + full read/write of the workspace.
    """
    return f"""(version 1)
(import "system.sb")
(allow process-fork)
(allow process-exec)
(allow network*)
(allow mach-lookup)
(allow sysctl-read)
; metadata for path resolution (cd, ls, stat — no content)
(allow file-read-metadata)
; system tool/library dirs needed for binary and dynamic linker
(allow file-read*
  (subpath "/usr") (subpath "/bin") (subpath "/sbin")
  (subpath "/System") (subpath "/Library") (subpath "/opt/homebrew")
  (subpath "/private/var/db/dyld") (subpath "/private/var/folders")
  (subpath "/private/var/select") (subpath "/dev")
  (subpath "/private/etc/ssl")
  ; Python 解释器自身的 prefix（venv + base），run_python 需读 site-packages 才能启动；
  ; 只读、限定到解释器目录，不放开整个 /Users
  (subpath "{_PY_PREFIX}") (subpath "{_PY_BASE_PREFIX}")
  (literal "/private/etc/hosts") (literal "/private/etc/resolv.conf"))
; workspace — kernel-gated: nothing outside this subpath can be read or written
(allow file-read* file-write* (subpath "{workspace_real}"))
"""


# ── Minimal environment for child processes ───────────────────────────

def _safe_env(workspace: str) -> dict[str, str]:
    """Return a minimal whitelist of env vars for exec'd processes.

    We DO NOT forward the host os.environ wholesale — that leaks
    API keys, secrets, JWT tokens, and other sensitive values.
    """
    tmp_dir = Path(workspace) / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": workspace,
        "WORKSPACE": workspace,
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        "TMPDIR": str(tmp_dir),
    }


def _workspace_relative_path(path: Path, workspace: Path) -> str:
    """Return a user-facing workspace-relative path without host prefixes."""
    if path.resolve() == workspace.resolve():
        return "."
    return str(path.resolve().relative_to(workspace.resolve()))


def _workspace_boundary_error() -> str:
    """Return a stable user-facing path boundary error."""
    return "Path escapes workspace boundary"


def _safe_external_filename(name: str, fallback: str = "file") -> str:
    """Collapse framework/user display names to a single safe file name."""
    cleaned = Path(str(name or "").replace("\\", "/")).name.strip()
    if cleaned in {"", ".", ".."}:
        return fallback
    return cleaned


def _read_capped_output(path: Path, label: str) -> tuple[str, bool]:
    """Read at most _MAX_OUTPUT_BYTES from a subprocess output file."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_OUTPUT_BYTES + 1)
    except FileNotFoundError:
        raw = b""
    truncated = len(raw) > _MAX_OUTPUT_BYTES
    if truncated:
        raw = raw[:_MAX_OUTPUT_BYTES]
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text += f"\n... [{label} truncated at 1MB]"
    return text, truncated


def _run_process_capped(
    argv: list[str],
    cwd: str,
    timeout: int,
    env: dict[str, str],
) -> dict[str, object]:
    """Run a subprocess while keeping returned stdout/stderr capped."""
    cwd_path = Path(cwd)
    token = uuid4().hex
    stdout_path = cwd_path / f".terminal_stdout_{token}.tmp"
    stderr_path = cwd_path / f".terminal_stderr_{token}.tmp"
    try:
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=timeout,
                env=env,
            )
        stdout, stdout_truncated = _read_capped_output(stdout_path, "stdout")
        stderr, stderr_truncated = _read_capped_output(stderr_path, "stderr")
        return {
            "return_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "timed_out": False,
            "error": "",
        }
    except subprocess.TimeoutExpired:
        stdout, stdout_truncated = _read_capped_output(stdout_path, "stdout")
        stderr, stderr_truncated = _read_capped_output(stderr_path, "stderr")
        return {
            "return_code": -1,
            "stdout": stdout,
            "stderr": stderr or f"Timeout after {timeout}s",
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "timed_out": True,
            "error": f"Command timed out after {timeout}s",
        }
    except Exception as exc:
        return {
            "return_code": -1,
            "stdout": "",
            "stderr": str(exc),
            "stdout_truncated": False,
            "stderr_truncated": False,
            "timed_out": False,
            "error": f"Command execution failed: {exc}",
        }
    finally:
        stdout_path.unlink(missing_ok=True)
        stderr_path.unlink(missing_ok=True)
