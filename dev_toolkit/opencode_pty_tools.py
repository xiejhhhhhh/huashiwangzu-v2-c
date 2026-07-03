"""PTY session tools for the project toolkit MCP server.

Split from ``opencode_tools.py`` to keep that file under 1000 lines.
"""

from __future__ import annotations

import json
import os
import pty
import select
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.types import Tool

try:
    from dev_toolkit.opencode_common import (
        DEFAULT_HOST,
        DEFAULT_PORT,
        now_slug,
        opencode_env,
        safe_title,
    )
    from dev_toolkit.opencode_tools import (
        _gateway_url,
        _opencode_binary,
        start_gateway,
    )
except ModuleNotFoundError:
    from opencode_common import (
        DEFAULT_HOST,
        DEFAULT_PORT,
        now_slug,
        opencode_env,
        safe_title,
    )
    from opencode_tools import (
        _gateway_url,
        _opencode_binary,
        start_gateway,
    )

TOOL_NAMES = {"opencode_pty_start", "opencode_pty_read", "opencode_pty_write", "opencode_pty_stop"}

_PTY_SESSIONS: dict[str, dict[str, Any]] = {}


def _pty_dir(repo_root: Path) -> Path:
    return repo_root / "backend" / "logs" / "opencode-pty"


def _append_log(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(data)


def _read_fd(fd: int, *, max_bytes: int = 12000, wait_seconds: float = 0.2) -> bytes:
    chunks: list[bytes] = []
    deadline = time.monotonic() + max(float(wait_seconds), 0.0)
    remaining = max(int(max_bytes), 1)
    while remaining > 0:
        timeout = max(deadline - time.monotonic(), 0.0)
        readable, _, _ = select.select([fd], [], [], timeout)
        if not readable:
            break
        try:
            data = os.read(fd, min(remaining, 4096))
        except (BlockingIOError, OSError):
            break
        if not data:
            break
        chunks.append(data)
        remaining -= len(data)
        if time.monotonic() >= deadline:
            break
    return b"".join(chunks)


def _decode_output(output: bytes) -> str:
    return output.decode("utf-8", errors="replace")


def _session_is_alive(session: dict[str, Any]) -> bool:
    process = session.get("process")
    return isinstance(process, subprocess.Popen) and process.poll() is None


def pty_start(
    repo_root: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    title: str = "",
    prompt: str = "",
    dangerously_skip_permissions: bool = True,
    use_proxy: bool = False,
) -> dict[str, Any]:
    binary = _opencode_binary()
    if not binary:
        return {"success": False, "error": "opencode binary not found in PATH"}
    status = start_gateway(repo_root, host=host, port=port)
    if not status.get("listening"):
        return {"success": False, "error": "opencode gateway is not listening", "gateway": status}

    clean_title = safe_title(title or "opencode-pty")
    cmd = [
        binary,
        "run",
        "--attach",
        _gateway_url(host, port),
        "--dir",
        str(repo_root),
        "--title",
        clean_title,
        "--interactive",
    ]
    if dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    if prompt:
        cmd.append(prompt)

    master_fd, slave_fd = pty.openpty()
    log_path = _pty_dir(repo_root) / f"{now_slug()}-{clean_title}.log"
    process = subprocess.Popen(
        cmd,
        cwd=str(repo_root),
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=opencode_env(use_proxy=use_proxy),
        start_new_session=True,
        close_fds=True,
    )
    os.close(slave_fd)
    os.set_blocking(master_fd, False)
    session_id = f"opencode-pty-{process.pid}"
    _PTY_SESSIONS[session_id] = {
        "process": process,
        "fd": master_fd,
        "log_path": log_path,
        "command": cmd,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    output = _read_fd(master_fd, max_bytes=12000, wait_seconds=1.0)
    if output:
        _append_log(log_path, output)
    return {
        "success": True,
        "session_id": session_id,
        "pid": process.pid,
        "alive": _session_is_alive(_PTY_SESSIONS[session_id]),
        "gateway_url": _gateway_url(host, port),
        "log_path": str(log_path),
        "command": cmd,
        "output": _decode_output(output),
        "dangerously_skip_permissions": dangerously_skip_permissions,
        "use_proxy": use_proxy,
    }


def pty_read(
    repo_root: Path, *, session_id: str, max_bytes: int = 12000, wait_seconds: float = 0.5
) -> dict[str, Any]:
    session = _PTY_SESSIONS.get(session_id)
    if not session:
        return {"success": False, "error": f"unknown opencode pty session: {session_id}"}
    fd = int(session["fd"])
    output = _read_fd(fd, max_bytes=max_bytes, wait_seconds=wait_seconds)
    if output:
        _append_log(Path(session["log_path"]), output)
    alive = _session_is_alive(session)
    if not alive:
        final_output = _read_fd(fd, max_bytes=max_bytes, wait_seconds=0.1)
        if final_output:
            _append_log(Path(session["log_path"]), final_output)
            output += final_output
    return {
        "success": True,
        "session_id": session_id,
        "alive": alive,
        "returncode": session["process"].poll(),
        "log_path": str(session["log_path"]),
        "output": _decode_output(output),
    }


def pty_write(
    repo_root: Path, *, session_id: str, text: str, enter: bool = True
) -> dict[str, Any]:
    session = _PTY_SESSIONS.get(session_id)
    if not session:
        return {"success": False, "error": f"unknown opencode pty session: {session_id}"}
    if not _session_is_alive(session):
        return {
            "success": False,
            "error": "opencode pty session is not alive",
            "returncode": session["process"].poll(),
        }
    data = (text + ("\n" if enter else "")).encode("utf-8")
    os.write(int(session["fd"]), data)
    _append_log(Path(session["log_path"]), data)
    output = _read_fd(int(session["fd"]), max_bytes=12000, wait_seconds=0.5)
    if output:
        _append_log(Path(session["log_path"]), output)
    return {
        "success": True,
        "session_id": session_id,
        "alive": _session_is_alive(session),
        "written_bytes": len(data),
        "log_path": str(session["log_path"]),
        "output": _decode_output(output),
    }


def pty_stop(repo_root: Path, *, session_id: str) -> dict[str, Any]:
    session = _PTY_SESSIONS.pop(session_id, None)
    if not session:
        return {"success": False, "error": f"unknown opencode pty session: {session_id}"}
    process = session["process"]
    fd = int(session["fd"])
    final_output = _read_fd(fd, max_bytes=24000, wait_seconds=0.2)
    if final_output:
        _append_log(Path(session["log_path"]), final_output)
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    final_output_after_exit = _read_fd(fd, max_bytes=24000, wait_seconds=0.2)
    if final_output_after_exit:
        _append_log(Path(session["log_path"]), final_output_after_exit)
        final_output += final_output_after_exit
    try:
        os.close(fd)
    except OSError:
        pass
    return {
        "success": True,
        "session_id": session_id,
        "returncode": process.poll(),
        "log_path": str(session["log_path"]),
        "final_output": _decode_output(final_output),
    }


def tool_definitions() -> list[Tool]:
    return [
        Tool(
            name="opencode_pty_start",
            description="启动一个可实时读写的 opencode PTY 会话，用于类似 SSH 的人工接管和调试。",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "default": DEFAULT_HOST},
                    "port": {"type": "number", "default": DEFAULT_PORT},
                    "title": {"type": "string", "default": ""},
                    "prompt": {"type": "string", "default": ""},
                    "dangerously_skip_permissions": {"type": "boolean", "default": True},
                    "use_proxy": {"type": "boolean", "default": False},
                },
            },
        ),
        Tool(
            name="opencode_pty_read",
            description="读取 opencode PTY 会话的最新屏幕输出。",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "max_bytes": {"type": "number", "default": 12000},
                    "wait_seconds": {"type": "number", "default": 0.5},
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="opencode_pty_write",
            description="向 opencode PTY 会话发送文本，默认追加回车。",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "text": {"type": "string"},
                    "enter": {"type": "boolean", "default": True},
                },
                "required": ["session_id", "text"],
            },
        ),
        Tool(
            name="opencode_pty_stop",
            description="停止并清理一个 opencode PTY 会话。",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    if name == "opencode_pty_start":
        return json.dumps(
            pty_start(
                repo_root,
                host=arguments.get("host", DEFAULT_HOST),
                port=int(arguments.get("port", DEFAULT_PORT)),
                title=arguments.get("title", ""),
                prompt=arguments.get("prompt", ""),
                dangerously_skip_permissions=bool(arguments.get("dangerously_skip_permissions", True)),
                use_proxy=bool(arguments.get("use_proxy", False)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_pty_read":
        return json.dumps(
            pty_read(
                repo_root,
                session_id=arguments["session_id"],
                max_bytes=int(arguments.get("max_bytes", 12000)),
                wait_seconds=float(arguments.get("wait_seconds", 0.5)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_pty_write":
        return json.dumps(
            pty_write(
                repo_root,
                session_id=arguments["session_id"],
                text=arguments["text"],
                enter=bool(arguments.get("enter", True)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_pty_stop":
        return json.dumps(
            pty_stop(repo_root, session_id=arguments["session_id"]),
            ensure_ascii=False,
            indent=2,
        )
    raise ValueError(f"未知 opencode PTY 工具: {name}")
