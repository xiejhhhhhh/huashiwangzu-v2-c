"""FastAPI router for terminal-tools module.

Exposes 6 cross-module capabilities:
  terminal-tools:exec          — Run shell commands in user workspace
  terminal-tools:write_file    — Write files into user workspace
  terminal-tools:read_file     — Read files from user workspace
  terminal-tools:list_workspace— List files in user workspace
  terminal-tools:publish       — Publish workspace files to framework FS
  terminal-tools:import        — Import framework FS files into workspace

All file operations are locked to the user's workspace directory.
Dangerous commands are intercepted.  Execution has timeout + output caps.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.middleware.auth import require_permission
from app.models.user import User
from app.models.file import File
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.config import get_settings
from app.core.exceptions import NotFound, AppException

logger = logging.getLogger("v2.terminal-tools")

router = APIRouter(prefix="/api/terminal-tools", tags=["terminal-tools"])

# ── Workspace configuration ─────────────────────────────────────────────
_WORKSPACE_ROOT = None
_MAX_OUTPUT_BYTES = 1 * 1024 * 1024   # 1 MB
_DEFAULT_TIMEOUT = 60                  # seconds


def _get_workspace_base() -> Path:
    """Return the root of all user workspaces (backend/data/workspaces/)."""
    global _WORKSPACE_ROOT
    if _WORKSPACE_ROOT is None:
        settings = get_settings()
        # UPLOAD_DIR = "data/uploads" — workspace lives alongside it
        base = Path(settings.UPLOAD_DIR).resolve().parent
        _WORKSPACE_ROOT = (base / "workspaces").resolve()
        _WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    return _WORKSPACE_ROOT


def _resolve_user_id(caller: str) -> int:
    """Extract user id from caller string like 'user:42'."""
    if caller.startswith("user:"):
        try:
            return int(caller.split(":", 1)[1])
        except ValueError:
            pass
    raise ValueError(f"Unknown caller format: {caller}")


def _user_workspace(user_id: int) -> Path:
    """Return and ensure the workspace directory for a given user."""
    ws = _get_workspace_base() / str(user_id)
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _resolve_workspace_path(user_id: int, relative_path: str) -> Path:
    """Normalise a relative path and verify it stays inside the user workspace.

    Raises ValueError if the path escapes the workspace boundary.
    """
    workspace_root = _user_workspace(user_id)
    # Clean path: strip leading slashes, reject empty / "." up-traversal tricks
    cleaned = relative_path.strip()
    if not cleaned or cleaned == ".":
        return workspace_root
    # Resolve the target path
    target = (workspace_root / cleaned).resolve()
    # Must be inside workspace root
    if not str(target).startswith(str(workspace_root)):
        raise ValueError(
            f"Path escapes workspace boundary: {relative_path!r}"
        )
    return target


# ── Dangerous command detection ─────────────────────────────────────────

# Patterns that are NEVER allowed, regardless of context
_DANGEROUS_PATTERNS = [
    # Privilege escalation
    r'\bsudo\b',
    r'\bsu\s',
    # System shutdown / reboot
    r'\b(shutdown|reboot|halt|poweroff|init\s+[06])\b',
    # Disk / filesystem destruction
    r'\bmkfs\b',
    r'\bdd\s+if=',
    r'\bfdisk\b',
    r'\bparted\b',
    r'\bmount\b',
    r'\bumount\b',
    # Dangerous recursive removal targeting root
    r'\brm\s+.*-rf\s+/',
    r'\brm\s+-rf\s+/',
    # Redirection to device files
    r'>\s*/dev/(sd|hd|nvme|mmcblk)',
    # Password / account manipulation
    r'\bpasswd\b',
    r'\bvisudo\b',
    r'\bchown\s+.*\s+/',
    r'\bchmod\s+777\s+/',
    # Fork bomb pattern
    r':\(\)\s*\{',
    r'fork\s+bomb',
]


def _check_dangerous_command(command: str) -> str | None:
    """Return an error message if the command is dangerous, else None."""
    cmd_lower = command.lower().strip()
    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower):
            return f"Dangerous command blocked: matched pattern '{pattern}'"
    return None


def _check_path_escape(command: str, workspace_real: str) -> str | None:
    """Check if command tries to access filesystem paths outside the workspace.

    Intercepts:
      - cd to absolute path outside workspace (cd /, cd /tmp)
      - cd with ~ expansion (cd ~, cd ~/Downloads)
      - cd .. traversal that exits workspace
      - ls / find / tree / cat etc. with absolute path outside workspace

    This is an application-layer guard; the kernel sandbox (sandbox-exec)
    remains the primary defence against content escape.
    """
    import shlex

    try:
        tokens = shlex.split(command)
    except ValueError:
        return None  # Malformed shell syntax, let shell handle

    if not tokens:
        return None

    cmd_name = tokens[0]
    args = tokens[1:]

    # Commands that traverse or read directory/filesystem metadata
    TRAVERSAL_CMDS = frozenset({
        'cd', 'ls', 'find', 'tree', 'cat', 'less', 'more',
        'head', 'tail', 'nl', 'wc', 'stat', 'du', 'file',
        'readlink', 'realpath', 'dirname',
    })

    if cmd_name not in TRAVERSAL_CMDS:
        return None

    for arg in args:
        # Skip flags and shell operators
        if arg.startswith('-') or arg in {'&&', '||', ';', '|', '>', '>>', '<'}:
            continue

        # Block ~ expansion (home directory is outside workspace)
        if arg == '~' or arg.startswith('~/'):
            return (f"Path escape blocked: '{arg}' expands to"
                    " home directory outside workspace")

        # Resolve the path relative to the workspace root
        try:
            resolved = os.path.realpath(os.path.join(workspace_real, arg))
        except (OSError, ValueError):
            continue

        resolved_str = str(resolved)
        ws_prefix = workspace_real.rstrip('/') + '/'
        if not resolved_str.startswith(ws_prefix) and resolved_str != workspace_real:
            return (f"Path escape blocked: '{arg}' resolves to"
                    f" {resolved_str} outside workspace")

    return None


# ── macOS sandbox-exec profile ────────────────────────────────────────

def _build_sandbox_profile(workspace_real: str) -> str:
    """Return a sandbox-exec profile string that locks the child process to
    read-only system + full read/write of the workspace.

    The profile is passed inline (-p) so the model cannot tamper with a
    sandbox file sitting in its own writable workspace.
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
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": workspace,
        "WORKSPACE": workspace,
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:exec
# ═══════════════════════════════════════════════════════════════════════
async def _exec(params: dict, caller: str) -> dict:
    """Execute a shell command inside a kernel-level sandbox on macOS.

    On macOS: wraps the child in sandbox-exec — read-only system,
    read/write only the user workspace.  No amount of model cleverness
    can escape the kernel sandbox.

    On Linux (no sandbox-exec): fail-closed — exec is disabled.
    """
    user_id = _resolve_user_id(caller)
    workspace = _user_workspace(user_id)
    workspace_real = os.path.realpath(str(workspace))
    command = params.get("command", "").strip()
    timeout = int(params.get("timeout", _DEFAULT_TIMEOUT))

    if not command:
        return {"success": False, "error": "No command provided"}

    # Cap timeout
    if timeout <= 0 or timeout > 600:
        timeout = _DEFAULT_TIMEOUT

    # Dangerous command check (keep — cheap second layer)
    danger = _check_dangerous_command(command)
    if danger:
        logger.warning(
            "user=%s blocked dangerous command: %s", user_id, command
        )
        return {
            "success": False,
            "error": danger,
            "command": command,
        }

    # Path escape check — prevent cd /, ls /etc, etc.
    escape = _check_path_escape(command, str(workspace_real))
    if escape:
        logger.warning(
            "user=%s blocked path escape: %s", user_id, command
        )
        return {
            "success": False,
            "error": escape,
            "command": command,
        }

    # Minimal env — no host secrets leaked
    safe_env = _safe_env(str(workspace_real))

    # ── Platform sandbox ──────────────────────────────────────────
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        # macOS kernel sandbox — gold standard
        profile = _build_sandbox_profile(workspace_real)
        argv = ["sandbox-exec", "-p", profile, "/bin/sh", "-c", command]
        cwd = workspace_real
    else:
        # No usable sandbox — fail-closed (do NOT exec unsandboxed)
        return {
            "success": False,
            "error": (
                "当前平台无可用沙盒(sandbox-exec/bwrap)，exec 已禁用。"
                "需要 macOS 或安装了 bubblewrap 的 Linux。"
            ),
            "command": command,
        }

    logger.info("user=%s exec(sandbox): %s", user_id, command[:200])

    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=safe_env,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Command timed out after {timeout}s",
            "timed_out": True,
            "return_code": -1,
            "stdout": "",
            "stderr": f"Timeout after {timeout}s",
            "command": command,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Command execution failed: {exc}",
            "return_code": -1,
            "stdout": "",
            "stderr": str(exc),
            "command": command,
        }

    # Truncate output
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    stdout_truncated = len(stdout) > _MAX_OUTPUT_BYTES
    stderr_truncated = len(stderr) > _MAX_OUTPUT_BYTES
    if stdout_truncated:
        stdout = stdout[:_MAX_OUTPUT_BYTES] + "\n... [stdout truncated at 1MB]"
    if stderr_truncated:
        stderr = stderr[:_MAX_OUTPUT_BYTES] + "\n... [stderr truncated at 1MB]"

    return {
        "success": proc.returncode == 0,
        "return_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "command": command,
    }


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:write_file
# ═══════════════════════════════════════════════════════════════════════
async def _write_file(params: dict, caller: str) -> dict:
    """Write content to a file in the user workspace."""
    user_id = _resolve_user_id(caller)
    path = params.get("path", "").strip()
    content = params.get("content", "")

    if not path:
        return {"success": False, "error": "No path provided"}

    try:
        target = _resolve_workspace_path(user_id, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except ValueError as exc:
        return {"success": False, "error": str(exc), "path": path}
    except Exception as exc:
        return {"success": False, "error": f"Write failed: {exc}", "path": path}

    return {
        "success": True,
        "path": str(target.relative_to(_user_workspace(user_id))),
        "absolute_path": str(target),
        "size": target.stat().st_size,
    }


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:read_file
# ═══════════════════════════════════════════════════════════════════════
async def _read_file(params: dict, caller: str) -> dict:
    """Read content from a file in the user workspace."""
    user_id = _resolve_user_id(caller)
    path = params.get("path", "").strip()

    if not path:
        return {"success": False, "error": "No path provided"}

    try:
        target = _resolve_workspace_path(user_id, path)
    except ValueError as exc:
        return {"success": False, "error": str(exc), "path": path}

    if not target.exists():
        return {"success": False, "error": f"File not found: {path}", "path": path}
    if not target.is_file():
        return {"success": False, "error": f"Not a file: {path}", "path": path}

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Try as binary and return size info for non-text files
        raw = target.read_bytes()
        return {
            "success": True,
            "path": path,
            "size": len(raw),
            "binary": True,
            "content": None,
            "note": "Binary file — cannot display as text",
        }
    except Exception as exc:
        return {"success": False, "error": f"Read failed: {exc}", "path": path}

    return {
        "success": True,
        "path": path,
        "size": len(content),
        "content": content,
        "binary": False,
    }


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:list_workspace
# ═══════════════════════════════════════════════════════════════════════
async def _list_workspace(params: dict, caller: str) -> dict:
    """List files and directories in the user workspace."""
    user_id = _resolve_user_id(caller)
    path = params.get("path", "").strip() or "."

    try:
        target = _resolve_workspace_path(user_id, path)
    except ValueError as exc:
        return {"success": False, "error": str(exc), "path": path}

    if not target.exists():
        return {"success": False, "error": f"Path not found: {path}", "path": path}
    if not target.is_dir():
        return {"success": False, "error": f"Not a directory: {path}", "path": path}

    items = []
    try:
        with os.scandir(target) as entries:
            for entry in entries:
                stat = entry.stat()
                items.append({
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "is_file": entry.is_file(),
                    "size": stat.st_size if entry.is_file() else 0,
                    "modified_at": stat.st_mtime,
                })
    except Exception as exc:
        return {"success": False, "error": f"List failed: {exc}", "path": path}

    # Sort: dirs first, then alphabetically
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

    return {
        "success": True,
        "path": str(target.relative_to(_user_workspace(user_id))) if target != _user_workspace(user_id) else ".",
        "items": items,
        "count": len(items),
    }


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:publish
# ═══════════════════════════════════════════════════════════════════════
async def _publish(params: dict, caller: str) -> dict:
    """Publish a workspace file to the framework file system (desktop-visible)."""
    from app.services import file_upload_service

    user_id = _resolve_user_id(caller)
    path = params.get("path", "").strip()
    display_name = params.get("filename", "").strip()
    folder_id = int(params.get("folder_id", 0)) if params.get("folder_id") else None

    if not path:
        return {"success": False, "error": "No path provided"}

    # Resolve and validate workspace file
    try:
        source = _resolve_workspace_path(user_id, path)
    except ValueError as exc:
        return {"success": False, "error": str(exc), "path": path}

    if not source.exists():
        return {"success": False, "error": f"File not found: {path}", "path": path}
    if not source.is_file():
        return {"success": False, "error": f"Not a file: {path}", "path": path}

    try:
        file_bytes = source.read_bytes()
    except Exception as exc:
        return {"success": False, "error": f"Read failed: {exc}", "path": path}

    # Determine the filename for the framework file system
    if display_name:
        filename = display_name
    else:
        filename = source.name

    target_folder = folder_id if (folder_id and folder_id > 0) else None

    # Upload via framework — content-addressable, dedup-aware
    try:
        async with AsyncSessionLocal() as db:
            result = await file_upload_service.upload_file(
                db,
                io.BytesIO(file_bytes),
                filename,
                user_id,
                target_folder,
            )
    except Exception as exc:
        return {"success": False, "error": f"Publish failed: {exc}", "path": path}

    return {
        "success": True,
        "file_id": result["id"],
        "name": result["name"],
        "extension": result["extension"],
        "size": result["size"],
        "mime_type": result["mime_type"],
        "deduplicated": result.get("deduplicated", False),
        "source_path": path,
    }


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:import
# ═══════════════════════════════════════════════════════════════════════
async def _import(params: dict, caller: str) -> dict:
    """Import a framework file into the user workspace."""
    from app.services import file_service, file_preview_service

    user_id = _resolve_user_id(caller)
    file_id = int(params.get("file_id", 0))
    target_path = params.get("target_path", "").strip()

    if file_id <= 0:
        return {"success": False, "error": "file_id must be a positive integer"}

    # Verify file exists and belongs to user
    async with AsyncSessionLocal() as db:
        file_record = await file_service.get_file_record(db, file_id)
        if not file_record:
            return {"success": False, "error": f"File not found: {file_id}"}
        if file_record.owner_id != user_id:
            return {
                "success": False,
                "error": "Access denied: file does not belong to current user",
            }

        # Resolve storage path on disk
        storage_path = file_preview_service._resolve_storage_path(file_record)
        if not storage_path:
            return {
                "success": False,
                "error": "File on disk not found — storage path invalid",
            }

        try:
            file_bytes = storage_path.read_bytes()
        except Exception as exc:
            return {
                "success": False,
                "error": f"Read disk file failed: {exc}",
            }

    # Determine target filename in workspace
    if target_path:
        filename = target_path
    else:
        ext = file_record.extension
        filename = f"{file_record.name}.{ext}" if ext else file_record.name

    # Write to workspace (path-constrained)
    try:
        target = _resolve_workspace_path(user_id, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file_bytes)
    except ValueError as exc:
        return {"success": False, "error": str(exc), "path": filename}

    return {
        "success": True,
        "path": str(target.relative_to(_user_workspace(user_id))),
        "absolute_path": str(target),
        "size": target.stat().st_size,
        "source_file_id": file_id,
        "source_file_name": f"{file_record.name}.{file_record.extension}"
        if file_record.extension
        else file_record.name,
    }


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:run_python — merged from data-analysis
# ═══════════════════════════════════════════════════════════════════════

_CHART_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}


def _build_python_exec_script(code: str, workspace_dir: str) -> str:
    return f"""import os, sys, io, json

os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg")

os.chdir({json.dumps(workspace_dir)})
sys.path.insert(0, {json.dumps(workspace_dir)})

{code}
"""


async def _run_python(params: dict, caller: str) -> dict:
    """Run Python code with pandas/numpy/matplotlib in user workspace.
    
    Reuses terminal-tools workspace isolation, timeout, and output truncation.
    Uses sandbox-exec on macOS (same as _exec), fail-closed on other platforms.
    Automatically collects plt.savefig() charts and uploads them to framework FS.
    """
    user_id = _resolve_user_id(caller)
    workspace = _user_workspace(user_id)
    workspace_real = str(workspace.resolve())
    code = params.get("code", "").strip()
    timeout = int(params.get("timeout", _DEFAULT_TIMEOUT))

    if not code:
        return {"success": False, "error": "No code provided"}
    if timeout <= 0 or timeout > 600:
        timeout = _DEFAULT_TIMEOUT

    # Copy input files into workspace
    input_file_ids = params.get("input_files", []) or []
    if input_file_ids:
        for fid in input_file_ids:
            file_id = int(fid)
            async with AsyncSessionLocal() as db:
                from app.services.file_service import check_file_access
                from app.services.file_preview_service import _resolve_storage_path
                try:
                    file_record = await check_file_access(db, file_id, user_id)
                except (NotFound, AppException) as exc:
                    return {"success": False, "error": f"Input file {file_id} access denied: {exc}"}
                src_path = _resolve_storage_path(file_record)
                if not src_path or not src_path.exists():
                    return {"success": False, "error": f"Input file {file_id} not found on disk"}
                target_name = f"{file_record.name}.{file_record.extension}" if file_record.extension else file_record.name
                target = workspace / target_name
                shutil.copy2(str(src_path), str(target))

    run_id = uuid.uuid4().hex[:12]
    run_dir = workspace / f".da_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    script_content = _build_python_exec_script(code, str(run_dir))
    script_path = run_dir / "script.py"
    script_path.write_text(script_content, encoding="utf-8")

    safe_env = _safe_env(str(workspace_real))
    safe_env["MPLBACKEND"] = "Agg"
    safe_env["PYTHONDONTWRITEBYTECODE"] = "1"

    logger.info("user=%s run_python (timeout=%ss, input_files=%s)", user_id, timeout, input_file_ids)

    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        profile = _build_sandbox_profile(workspace_real)
        argv = ["sandbox-exec", "-p", profile, sys.executable, str(script_path)]
        cwd = str(run_dir)
    else:
        return {
            "success": False,
            "error": (
                "当前平台无可用沙盒(sandbox-exec)，run_python 已禁用。"
                "需要 macOS 或安装了 bubblewrap 的 Linux。"
            ),
            "code_preview": code[:200],
        }

    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=safe_env,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(str(run_dir), ignore_errors=True)
        return {"success": False, "error": f"Execution timed out after {timeout}s", "timed_out": True, "stdout": "", "stderr": f"Timeout after {timeout}s"}
    except Exception as exc:
        shutil.rmtree(str(run_dir), ignore_errors=True)
        return {"success": False, "error": f"Execution failed: {exc}", "stdout": "", "stderr": str(exc)}

    # Collect generated chart files
    charts = []
    for fpath in run_dir.iterdir():
        if fpath.is_file() and fpath.suffix.lower() in _CHART_EXTENSIONS:
            try:
                file_bytes = fpath.read_bytes()
                async with AsyncSessionLocal() as db:
                    from app.services import file_upload_service
                    result = await file_upload_service.upload_file(
                        db, io.BytesIO(file_bytes), fpath.name, user_id, None,
                    )
                    charts.append({
                        "file_id": result["id"],
                        "name": result["name"],
                        "size": result["size"],
                        "deduplicated": result.get("deduplicated", False),
                    })
            except Exception as exc:
                logger.warning("user=%s failed to upload chart %s: %s", user_id, fpath.name, exc)

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    stdout_truncated = len(stdout) > _MAX_OUTPUT_BYTES
    stderr_truncated = len(stderr) > _MAX_OUTPUT_BYTES
    if stdout_truncated:
        stdout = stdout[:_MAX_OUTPUT_BYTES] + "\n... [stdout truncated at 1MB]"
    if stderr_truncated:
        stderr = stderr[:_MAX_OUTPUT_BYTES] + "\n... [stderr truncated at 1MB]"

    shutil.rmtree(str(run_dir), ignore_errors=True)

    return {
        "success": proc.returncode == 0,
        "return_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "charts": charts,
        "chart_count": len(charts),
    }


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:chart — simplified chart generation
# ═══════════════════════════════════════════════════════════════════════
async def _chart(params: dict, caller: str) -> dict:
    """Foolproof chart generation: sends data + chart_type, gets a chart file."""
    data = params.get("data", [])
    chart_type = params.get("chart_type", "line")
    title = params.get("title", "")
    x_label = params.get("x_label", "")
    y_label = params.get("y_label", "")

    if not data:
        return {"success": False, "error": "No data provided"}
    if chart_type not in ("line", "bar", "pie"):
        return {"success": False, "error": f"Unsupported chart type: {chart_type}"}

    script_lines = [
        "import matplotlib",
        'matplotlib.use("Agg")',
        "import matplotlib.pyplot as plt",
        "import json",
        "",
        f"data = {json.dumps(data)}",
        f"title = {json.dumps(title)}",
        f"x_label = {json.dumps(x_label)}",
        f"y_label = {json.dumps(y_label)}",
        "",
    ]

    if chart_type == "pie":
        script_lines.extend([
            "labels = [str(d.get('x', d.get('label', ''))) for d in data]",
            "values = [float(d.get('y', d.get('value', 0))) for d in data]",
            "fig, ax = plt.subplots(figsize=(10, 8))",
            "ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)",
            "ax.axis('equal')",
        ])
    elif chart_type in ("line", "bar"):
        script_lines.extend([
            "xs = [str(d.get('x', '')) for d in data]",
            "ys = [float(d.get('y', 0)) for d in data]",
            "fig, ax = plt.subplots(figsize=(12, 6))",
        ])
        if chart_type == "line":
            script_lines.extend([
                "ax.plot(xs, ys, marker='o', linewidth=2, markersize=6)",
                "ax.grid(True, linestyle='--', alpha=0.6)",
            ])
        else:
            script_lines.extend([
                "ax.bar(xs, ys, color='#2395bc', edgecolor='white', linewidth=0.5)",
            ])

    script_lines.extend([
        "if title:",
        "    ax.set_title(title, fontsize=14, pad=15)",
        "if x_label:",
        "    ax.set_xlabel(x_label)",
        "if y_label:",
        "    ax.set_ylabel(y_label)",
        "",
        "plt.xticks(rotation=45, ha='right')",
        "plt.tight_layout()",
        'plt.savefig("chart.png", dpi=150)',
        'print(f"Chart saved: chart.png")',
    ])

    script = "\n".join(script_lines)
    exec_params = {"code": script, "timeout": 30}
    return await _run_python(exec_params, caller)


# ═══════════════════════════════════════════════════════════════════════
# Register capabilities with framework
# ═══════════════════════════════════════════════════════════════════════

register_capability(
    "terminal-tools",
    "exec",
    _exec,
    description="在用户工作区执行 shell 命令。受危险命令拦截、超时(默认60s)、输出1MB上限保护。cwd 锁定在用户工作区。返回 stdout/stderr/return_code。",
    brief="执行 shell 命令",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令",
            },
            "timeout": {
                "type": "integer",
                "description": "超时秒数（默认 60s，最大 600s）",
                "default": 60,
            },
        },
        "required": ["command"],
    },
    min_role="editor",
)

register_capability(
    "terminal-tools",
    "write_file",
    _write_file,
    description="写文件到用户工作区。路径自动约束在工作区内，越界路径被拒绝。",
    brief="写文件到工作区",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "工作区内的相对路径",
            },
            "content": {
                "type": "string",
                "description": "文件内容（UTF-8）",
            },
        },
        "required": ["path", "content"],
    },
    min_role="editor",
)

register_capability(
    "terminal-tools",
    "read_file",
    _read_file,
    description="读用户工作区内的文件内容。文本文件返回 UTF-8 内容，二进制文件返回大小信息。路径约束在工作区内。",
    brief="读取工作区文件",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "工作区内的相对路径",
            },
        },
        "required": ["path"],
    },
    min_role="viewer",
)

register_capability(
    "terminal-tools",
    "list_workspace",
    _list_workspace,
    description="列出用户工作区内的文件和目录。目录优先，按名称排序。",
    brief="列出工作区文件",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "工作区内的相对路径（默认根目录）",
                "default": ".",
            },
        },
    },
    min_role="viewer",
)

register_capability(
    "terminal-tools",
    "publish",
    _publish,
    description="将工作区文件显式交付到框架文件系统（桌面可见）。享受框架内容去重。返回框架文件 ID。",
    brief="文件发布到桌面",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "工作区内的相对路径",
            },
            "filename": {
                "type": "string",
                "description": "交付后的显示名称（可选，默认用原文件名）",
            },
            "folder_id": {
                "type": "integer",
                "description": "目标文件夹 ID（可选，默认桌面根目录）",
            },
        },
        "required": ["path"],
    },
    min_role="editor",
)

register_capability(
    "terminal-tools",
    "import",
    _import,
    description="将框架文件系统的文件拷入工作区供 CLI 处理。owner 校验：只能 import 自己的文件。",
    brief="导入文件到工作区",
    parameters={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "integer",
                "description": "框架文件 ID",
            },
            "target_path": {
                "type": "string",
                "description": "工作区内的目标相对路径（可选，默认用原文件名）",
            },
        },
        "required": ["file_id"],
    },
    min_role="editor",
)

register_capability(
    "terminal-tools",
    "run_python",
    _run_python,
    brief="运行 Python 代码",
    description=(
        "在用户工作区子进程执行 Python 数据分析代码。预置 pandas/numpy/matplotlib（Agg 后端）。"
        "代码用 plt.savefig() 存图、print() 输出文本。自动收集生成的图表文件并存入框架文件系统。"
        "input_files 传入 file_id 列表，框架自动备到工作区供代码读取。"
        "超时/输出截断复用 terminal-tools 保护。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "要执行的 Python 代码。可用 pandas/numpy/matplotlib（Agg 后端）。用 plt.savefig() 出图、print() 输出文本。"},
            "input_files": {"type": "array", "items": {"type": "integer"}, "description": "输入文件 file_id 列表（可选），备到工作区供代码读取"},
            "timeout": {"type": "integer", "description": "超时秒数（默认 60s，最大 600s）", "default": 60},
        },
        "required": ["code"],
    },
    min_role="editor",
)

register_capability(
    "terminal-tools",
    "chart",
    _chart,
    description="傻瓜式出图。传入数据数组和图表类型，后端用 matplotlib 直接出图存文件。支持折线(line)/柱状(bar)/饼图(pie)。",
    brief="自动生成图表",
    parameters={
        "type": "object",
        "properties": {
            "data": {"type": "array", "description": "数据数组，每个元素含 x/y 字段：[{x:'一月', y:100}, ...]"},
            "chart_type": {"type": "string", "enum": ["line", "bar", "pie"], "description": "line(折线)/bar(柱状)/pie(饼图)"},
            "title": {"type": "string", "description": "图表标题（可选）"},
            "x_label": {"type": "string", "description": "X 轴标签（可选）"},
            "y_label": {"type": "string", "description": "Y 轴标签（可选）"},
        },
        "required": ["data", "chart_type"],
    },
    min_role="editor",
)


# ═══════════════════════════════════════════════════════════════════════
# HTTP endpoints — for direct testing / sandbox debugging
# ═══════════════════════════════════════════════════════════════════════

class ExecRequest(BaseModel):
    command: str
    timeout: int = _DEFAULT_TIMEOUT


class WriteFileRequest(BaseModel):
    path: str
    content: str = ""


class ReadFileRequest(BaseModel):
    path: str


class ListWorkspaceRequest(BaseModel):
    path: str = "."


class PublishRequest(BaseModel):
    path: str
    filename: str = ""
    folder_id: int = 0


class ImportFileRequest(BaseModel):
    file_id: int
    target_path: str = ""


class RunPythonRequest(BaseModel):
    code: str
    input_files: list[int] = []
    timeout: int = _DEFAULT_TIMEOUT


class ChartDataPoint(BaseModel):
    x: str | float = ""
    y: float = 0


class ChartRequest(BaseModel):
    data: list[ChartDataPoint]
    chart_type: str = "line"
    title: str = ""
    x_label: str = ""
    y_label: str = ""


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "terminal-tools", "status": "ok"})


@router.post("/exec")
async def http_exec(
    body: ExecRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _exec(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/write-file")
async def http_write_file(
    body: WriteFileRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _write_file(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/read-file")
async def http_read_file(
    body: ReadFileRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _read_file(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/list-workspace")
async def http_list_workspace(
    body: ListWorkspaceRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _list_workspace(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/publish")
async def http_publish(
    body: PublishRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _publish(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/import")
async def http_import(
    body: ImportFileRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _import(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/run-python")
async def http_run_python(
    body: RunPythonRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _run_python(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/chart")
async def http_chart(
    body: ChartRequest,
    user: User = Depends(require_permission("editor")),
):
    result = await _chart(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)
