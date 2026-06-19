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
import os
import re
import subprocess
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


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:exec
# ═══════════════════════════════════════════════════════════════════════
async def _exec(params: dict, caller: str) -> dict:
    """Execute a shell command inside the user workspace."""
    user_id = _resolve_user_id(caller)
    workspace = _user_workspace(user_id)
    command = params.get("command", "").strip()
    timeout = int(params.get("timeout", _DEFAULT_TIMEOUT))

    if not command:
        return {"success": False, "error": "No command provided"}

    # Cap timeout
    if timeout <= 0 or timeout > 600:
        timeout = _DEFAULT_TIMEOUT

    # Dangerous command check
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

    logger.info("user=%s exec: %s", user_id, command[:200])

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **os.environ,
                "HOME": str(workspace),
                "WORKSPACE": str(workspace),
            },
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
# Register capabilities with framework
# ═══════════════════════════════════════════════════════════════════════

register_capability(
    "terminal-tools",
    "exec",
    _exec,
    description="在用户工作区执行 shell 命令。受危险命令拦截、超时(默认60s)、输出1MB上限保护。cwd 锁定在用户工作区。返回 stdout/stderr/return_code。",
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
