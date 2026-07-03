"""Shell command execution capability for terminal-tools.

Capability: terminal-tools:exec — Run shell commands in user workspace.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys

from .sandbox import (
    _DEFAULT_TIMEOUT,
    _build_sandbox_profile,
    _check_dangerous_command,
    _check_path_escape,
    _coerce_timeout,
    _resolve_user_id,
    _run_process_capped,
    _safe_env,
    _user_workspace,
)

logger = logging.getLogger("v2.terminal-tools")


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
    timeout = _coerce_timeout(params.get("timeout", _DEFAULT_TIMEOUT))

    if not command:
        return {"success": False, "error": "No command provided"}

    danger = _check_dangerous_command(command)
    if danger:
        logger.warning("user=%s blocked dangerous command: %s", user_id, command)
        return {"success": False, "error": danger, "command": command}

    escape = _check_path_escape(command, str(workspace_real))
    if escape:
        logger.warning("user=%s blocked path escape: %s", user_id, command)
        return {"success": False, "error": escape, "command": command}

    safe_env = _safe_env(str(workspace_real))

    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        profile = _build_sandbox_profile(workspace_real)
        argv = ["sandbox-exec", "-p", profile, "/bin/sh", "-c", command]
        cwd = workspace_real
    else:
        return {
            "success": False,
            "error": (
                "当前平台无可用沙盒(sandbox-exec)，exec 已禁用。"
                "当前实现需要 macOS sandbox-exec。"
            ),
            "command": command,
        }

    logger.info("user=%s exec(sandbox): %s", user_id, command[:200])

    result = _run_process_capped(argv, cwd, timeout, safe_env)
    if result["timed_out"]:
        return {
            "success": False,
            "error": result["error"],
            "timed_out": True,
            "return_code": result["return_code"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "stdout_truncated": result["stdout_truncated"],
            "stderr_truncated": result["stderr_truncated"],
            "command": command,
        }
    if result["error"]:
        return {
            "success": False,
            "error": result["error"],
            "return_code": result["return_code"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "stdout_truncated": result["stdout_truncated"],
            "stderr_truncated": result["stderr_truncated"],
            "command": command,
        }

    return {
        "success": result["return_code"] == 0,
        "return_code": result["return_code"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "stdout_truncated": result["stdout_truncated"],
        "stderr_truncated": result["stderr_truncated"],
        "command": command,
    }
