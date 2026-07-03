"""opencode gateway and mailbox dispatch tools for the project toolkit."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dev_toolkit import opencode_queue
    from dev_toolkit.opencode_common import (
        now_slug as _now_slug,
    )
    from dev_toolkit.opencode_common import (
        opencode_env as _opencode_env,
    )
    from dev_toolkit.opencode_common import (
        safe_title as _safe_title,
    )
except ModuleNotFoundError:
    import opencode_queue
    from opencode_common import (
        now_slug as _now_slug,
    )
    from opencode_common import (
        opencode_env as _opencode_env,
    )
    from opencode_common import (
        safe_title as _safe_title,
    )

TOOL_NAMES = {
    "opencode_gateway_status",
    "opencode_gateway_start",
    "opencode_list_letters",
    "opencode_dispatch_letter",
    "opencode_sdk_smoke",
    "opencode_sdk_prompt",
    "opencode_sdk_dispatch_letter",
    "opencode_sdk_messages",
    "opencode_sdk_job_submit",
    "opencode_sdk_job_dispatch_letter",
    "opencode_sdk_job_status",
    "opencode_sdk_job_list",
    "opencode_sdk_job_continue",
    "opencode_sdk_job_notifications",
}

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 55891
MAILBOX_NAME = "华世王镞_v2邮箱"
LOCAL_NO_PROXY = "127.0.0.1,localhost,::1"
DEFAULT_HTTP_PROXY = "http://127.0.0.1:4780"
DEFAULT_SDK_PACKAGE = "@opencode-ai/sdk@1.17.13"


def _gateway_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}"


def _logs_dir(repo_root: Path) -> Path:
    return repo_root / "backend" / "logs"


def _server_pid_path(repo_root: Path) -> Path:
    return _logs_dir(repo_root) / "opencode-server.pid"


def _server_log_path(repo_root: Path) -> Path:
    return _logs_dir(repo_root) / "opencode-server.log"


def _dispatch_dir(repo_root: Path) -> Path:
    return _logs_dir(repo_root) / "opencode-dispatches"


def _sdk_dir(repo_root: Path) -> Path:
    return _logs_dir(repo_root) / "opencode-sdk"


def _sdk_script(repo_root: Path) -> Path:
    return repo_root / "dev_toolkit" / "opencode_sdk_client.mjs"


def _outbox_dir(repo_root: Path) -> Path:
    return repo_root.parent / MAILBOX_NAME / "投递箱"


def _is_listening(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _listener_pid(port: int) -> str | None:
    lsof = shutil.which("lsof")
    if not lsof:
        return None
    completed = subprocess.run(
        [lsof, "-ti", f":{port}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return next((line.strip() for line in completed.stdout.splitlines() if line.strip()), None)


def _tail(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace")
    return data[-limit:]


def _opencode_binary() -> str | None:
    return shutil.which("opencode")


def _opencode_version(binary: str | None = None) -> str | None:
    executable = binary or _opencode_binary()
    if not executable:
        return None
    completed = subprocess.run(
        [executable, "--version"],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _serve_command(binary: str, host: str, port: int) -> list[str]:
    return [binary, "serve", "--hostname", host, "--port", str(port)]


def _resolve_letter(repo_root: Path, letter: str) -> Path:
    raw = Path(letter)
    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        name = letter if letter.endswith(".md") else f"{letter}.md"
        candidate = (_outbox_dir(repo_root) / name).resolve()
    outbox = _outbox_dir(repo_root).resolve()
    if not candidate.is_relative_to(outbox):
        raise ValueError("letter must be inside mailbox outbox")
    if not candidate.exists():
        raise FileNotFoundError(f"Letter not found: {candidate}")
    return candidate


def gateway_status(repo_root: Path, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict[str, Any]:
    pid_path = _server_pid_path(repo_root)
    log_path = _server_log_path(repo_root)
    pid = pid_path.read_text(encoding="utf-8").strip() if pid_path.exists() else ""
    listening = _is_listening(host, port)
    listener_pid = _listener_pid(port) if listening else None
    binary = _opencode_binary()
    return {
        "success": True,
        "listening": listening,
        "url": _gateway_url(host, port),
        "host": host,
        "port": port,
        "pid": pid or None,
        "listener_pid": listener_pid,
        "pid_path": str(pid_path),
        "log_path": str(log_path),
        "log_tail": _tail(log_path),
        "opencode_binary": binary,
        "opencode_version": _opencode_version(binary),
    }


def start_gateway(repo_root: Path, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict[str, Any]:
    status = gateway_status(repo_root, host=host, port=port)
    if status["listening"]:
        if status.get("listener_pid"):
            _server_pid_path(repo_root).write_text(str(status["listener_pid"]), encoding="utf-8")
            status["pid"] = status["listener_pid"]
        status["already_running"] = True
        return status

    binary = _opencode_binary()
    if not binary:
        return {"success": False, "error": "opencode binary not found in PATH"}

    log_path = _server_log_path(repo_root)
    pid_path = _server_pid_path(repo_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8")
    command = _serve_command(binary, host, port)
    process = subprocess.Popen(
        command,
        cwd=str(repo_root),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=_opencode_env(use_proxy=False),
        start_new_session=True,
    )
    pid_path.write_text(str(process.pid), encoding="utf-8")
    log_file.close()

    listening = False
    for _ in range(30):
        if _is_listening(host, port, timeout=0.2):
            listening = True
            break
        time.sleep(0.2)
    return {
        "success": listening,
        "started": True,
        "listening": listening,
        "url": _gateway_url(host, port),
        "pid": process.pid,
        "listener_pid": _listener_pid(port) if listening else None,
        "pid_path": str(pid_path),
        "log_path": str(log_path),
        "log_tail": _tail(log_path),
        "command": command,
    }


def list_letters(repo_root: Path, *, target_contains: str = "", limit: int = 50) -> dict[str, Any]:
    outbox = _outbox_dir(repo_root)
    letters = []
    if outbox.exists():
        for path in sorted(outbox.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
            if target_contains and target_contains not in path.name:
                continue
            letters.append({
                "name": path.name,
                "path": str(path),
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            })
            if len(letters) >= max(int(limit), 1):
                break
    return {"success": True, "outbox": str(outbox), "count": len(letters), "letters": letters}


def _node_binary() -> str | None:
    return shutil.which("node")


def _npm_binary() -> str | None:
    return shutil.which("npm")


def _ensure_sdk_package(repo_root: Path) -> dict[str, Any]:
    sdk_package = repo_root / ".opencode" / "node_modules" / "@opencode-ai" / "sdk"
    if sdk_package.exists():
        return {"success": True, "installed": False, "path": str(sdk_package)}
    npm = _npm_binary()
    if not npm:
        return {"success": False, "error": "npm binary not found in PATH"}
    completed = subprocess.run(
        [npm, "install", DEFAULT_SDK_PACKAGE, "--prefix", ".opencode"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        timeout=120,
        env=_opencode_env(use_proxy=False),
        stdin=subprocess.DEVNULL,
        check=False,
    )
    return {
        "success": completed.returncode == 0 and sdk_package.exists(),
        "installed": completed.returncode == 0 and sdk_package.exists(),
        "path": str(sdk_package),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _run_sdk(repo_root: Path, payload: dict[str, Any], *, timeout_seconds: int = 1800) -> dict[str, Any]:
    node = _node_binary()
    if not node:
        return {"success": False, "error": "node binary not found in PATH"}
    sdk_script = _sdk_script(repo_root)
    if not sdk_script.exists():
        return {"success": False, "error": f"SDK helper not found: {sdk_script}"}
    sdk_ready = _ensure_sdk_package(repo_root)
    if not sdk_ready.get("success"):
        return {"success": False, "error": "@opencode-ai/sdk is not installed", "sdk_install": sdk_ready}
    payload = {
        "directory": str(repo_root),
        **payload,
    }
    command = [node, str(sdk_script), json.dumps(payload, ensure_ascii=False)]
    completed = subprocess.run(
        command,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        timeout=max(int(timeout_seconds), 1),
        env=_opencode_env(use_proxy=False),
        stdin=subprocess.DEVNULL,
        check=False,
    )
    log_root = _sdk_dir(repo_root)
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / f"{_now_slug()}-{_safe_title(str(payload.get('action', 'sdk')))}.json"
    log_path.write_text((completed.stdout or "") + (completed.stderr or ""), encoding="utf-8")
    try:
        data = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        data = {
            "success": False,
            "error": "SDK helper returned non-JSON output",
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    data.setdefault("success", completed.returncode == 0)
    data["returncode"] = completed.returncode
    data["log_path"] = str(log_path)
    return data


def sdk_smoke(
    repo_root: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    prompt: str = "",
    title: str = "",
    username: str = "",
    password: str = "",
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    status = start_gateway(repo_root, host=host, port=port)
    if not status.get("listening"):
        return {"success": False, "error": "opencode gateway is not listening", "gateway": status}
    return _run_sdk(
        repo_root,
        {
            "action": "smoke",
            "host": host,
            "port": port,
            "prompt": prompt,
            "title": title,
            "username": username or None,
            "password": password or None,
        },
        timeout_seconds=timeout_seconds,
    )


def sdk_prompt(
    repo_root: Path,
    *,
    prompt: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    title: str = "",
    session_id: str = "",
    agent: str = "",
    username: str = "",
    password: str = "",
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    status = start_gateway(repo_root, host=host, port=port)
    if not status.get("listening"):
        return {"success": False, "error": "opencode gateway is not listening", "gateway": status}
    return _run_sdk(
        repo_root,
        {
            "action": "prompt",
            "host": host,
            "port": port,
            "prompt": prompt,
            "title": title,
            "session_id": session_id or None,
            "agent": agent or None,
            "username": username or None,
            "password": password or None,
        },
        timeout_seconds=timeout_seconds,
    )


def sdk_dispatch_letter(
    repo_root: Path,
    *,
    letter: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    title: str = "",
    session_id: str = "",
    agent: str = "",
    username: str = "",
    password: str = "",
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    status = start_gateway(repo_root, host=host, port=port)
    if not status.get("listening"):
        return {"success": False, "error": "opencode gateway is not listening", "gateway": status}
    letter_path = _resolve_letter(repo_root, letter)
    return _run_sdk(
        repo_root,
        {
            "action": "dispatch_letter",
            "host": host,
            "port": port,
            "letter_path": str(letter_path),
            "letter_title": letter_path.stem,
            "title": title,
            "session_id": session_id or None,
            "agent": agent or None,
            "username": username or None,
            "password": password or None,
        },
        timeout_seconds=timeout_seconds,
    )


def sdk_messages(
    repo_root: Path,
    *,
    session_id: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    limit: int = 50,
    username: str = "",
    password: str = "",
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    status = start_gateway(repo_root, host=host, port=port)
    if not status.get("listening"):
        return {"success": False, "error": "opencode gateway is not listening", "gateway": status}
    return _run_sdk(
        repo_root,
        {
            "action": "messages",
            "host": host,
            "port": port,
            "session_id": session_id,
            "limit": limit,
            "username": username or None,
            "password": password or None,
        },
        timeout_seconds=timeout_seconds,
    )


def dispatch_letter(
    repo_root: Path,
    *,
    letter: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    title: str = "",
    background: bool = True,
    timeout_seconds: int = 1800,
    dangerously_skip_permissions: bool = True,
    use_proxy: bool = False,
) -> dict[str, Any]:
    binary = _opencode_binary()
    if not binary:
        return {"success": False, "error": "opencode binary not found in PATH"}
    status = start_gateway(repo_root, host=host, port=port)
    if not status.get("listening"):
        return {"success": False, "error": "opencode gateway is not listening", "gateway": status}

    letter_path = _resolve_letter(repo_root, letter)
    clean_title = _safe_title(title or letter_path.stem)
    prompt = f"请读取并执行：{letter_path}"
    cmd = [
        binary,
        "run",
        "--attach",
        _gateway_url(host, port),
        "--dir",
        str(repo_root),
        "--title",
        clean_title,
        "--format",
        "json",
    ]
    if dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    cmd.append(
        prompt,
    )

    dispatch_root = _dispatch_dir(repo_root)
    dispatch_root.mkdir(parents=True, exist_ok=True)
    log_path = dispatch_root / f"{_now_slug()}-{_safe_title(letter_path.stem)}.log"
    env = _opencode_env(use_proxy=use_proxy)

    if background:
        log_file = log_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        log_file.close()
        time.sleep(0.5)
        returncode = process.poll()
        return {
            "success": returncode is None,
            "background": True,
            "pid": process.pid,
            "returncode": returncode,
            "letter": str(letter_path),
            "gateway_url": _gateway_url(host, port),
            "log_path": str(log_path),
            "log_tail": _tail(log_path),
            "command": cmd,
            "dangerously_skip_permissions": dangerously_skip_permissions,
            "use_proxy": use_proxy,
        }

    completed = subprocess.run(
        cmd,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        timeout=max(int(timeout_seconds), 1),
        env=env,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    log_path.write_text((completed.stdout or "") + (completed.stderr or ""), encoding="utf-8")
    return {
        "success": completed.returncode == 0,
        "background": False,
        "returncode": completed.returncode,
        "letter": str(letter_path),
        "gateway_url": _gateway_url(host, port),
        "log_path": str(log_path),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "dangerously_skip_permissions": dangerously_skip_permissions,
        "use_proxy": use_proxy,
    }


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="opencode_gateway_status",
            description="查看本机 opencode headless 网关状态，默认 http://127.0.0.1:55891。",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "default": DEFAULT_HOST},
                    "port": {"type": "number", "default": DEFAULT_PORT},
                },
            },
        ),
        Tool(
            name="opencode_gateway_start",
            description="启动本机 opencode headless 网关，默认 55891 端口；已启动则直接返回状态。",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "default": DEFAULT_HOST},
                    "port": {"type": "number", "default": DEFAULT_PORT},
                },
            },
        ),
        Tool(
            name="opencode_list_letters",
            description="列出邮箱投递箱中的 Markdown 任务信。",
            inputSchema={
                "type": "object",
                "properties": {
                    "target_contains": {"type": "string", "default": ""},
                    "limit": {"type": "number", "default": 50},
                },
            },
        ),
        Tool(
            name="opencode_dispatch_letter",
            description="把一封投递箱任务信派发给 opencode run --attach；默认后台执行并写日志。",
            inputSchema={
                "type": "object",
                "properties": {
                    "letter": {"type": "string", "description": "投递箱文件名或绝对路径"},
                    "host": {"type": "string", "default": DEFAULT_HOST},
                    "port": {"type": "number", "default": DEFAULT_PORT},
                    "title": {"type": "string", "default": ""},
                    "background": {"type": "boolean", "default": True},
                    "timeout_seconds": {"type": "number", "default": 1800},
                    "dangerously_skip_permissions": {
                        "type": "boolean",
                        "default": True,
                        "description": "自动批准 opencode 子代理读写项目所需权限，适合受投递信边界约束的维修任务。",
                    },
                    "use_proxy": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否给 opencode 子进程注入 127.0.0.1:4780 HTTP/HTTPS 代理；本机 attach 默认不走代理。",
                    },
                },
                "required": ["letter"],
            },
        ),
        Tool(
            name="opencode_sdk_smoke",
            description="用官方 @opencode-ai/sdk 直连 opencode server 做最小冒烟：创建 session、发 prompt、返回最终消息。",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "default": DEFAULT_HOST},
                    "port": {"type": "number", "default": DEFAULT_PORT},
                    "prompt": {"type": "string", "default": "只输出 OK，不要解释。"},
                    "title": {"type": "string", "default": "opencode-sdk-smoke"},
                    "username": {"type": "string", "default": ""},
                    "password": {"type": "string", "default": ""},
                    "timeout_seconds": {"type": "number", "default": 1800},
                },
            },
        ),
        Tool(
            name="opencode_sdk_prompt",
            description="用官方 @opencode-ai/sdk 发送 prompt；返回 session/message/tokens/cost/文本，可用 session_id 继续同一会话。",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "host": {"type": "string", "default": DEFAULT_HOST},
                    "port": {"type": "number", "default": DEFAULT_PORT},
                    "title": {"type": "string", "default": ""},
                    "session_id": {"type": "string", "default": ""},
                    "agent": {"type": "string", "default": ""},
                    "username": {"type": "string", "default": ""},
                    "password": {"type": "string", "default": ""},
                    "timeout_seconds": {"type": "number", "default": 1800},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="opencode_sdk_dispatch_letter",
            description="用官方 @opencode-ai/sdk 派发投递箱任务信；稳定返回 session/message，替代 PTY/CLI 黑盒派发。",
            inputSchema={
                "type": "object",
                "properties": {
                    "letter": {"type": "string", "description": "投递箱文件名或绝对路径"},
                    "host": {"type": "string", "default": DEFAULT_HOST},
                    "port": {"type": "number", "default": DEFAULT_PORT},
                    "title": {"type": "string", "default": ""},
                    "session_id": {"type": "string", "default": ""},
                    "agent": {"type": "string", "default": ""},
                    "username": {"type": "string", "default": ""},
                    "password": {"type": "string", "default": ""},
                    "timeout_seconds": {"type": "number", "default": 1800},
                },
                "required": ["letter"],
            },
        ),
        Tool(
            name="opencode_sdk_messages",
            description="用官方 @opencode-ai/sdk 按 session_id 读取消息历史，用于随时跟踪派发状态和最终输出。",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "host": {"type": "string", "default": DEFAULT_HOST},
                    "port": {"type": "number", "default": DEFAULT_PORT},
                    "limit": {"type": "number", "default": 50},
                    "username": {"type": "string", "default": ""},
                    "password": {"type": "string", "default": ""},
                    "timeout_seconds": {"type": "number", "default": 60},
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="opencode_sdk_job_submit",
            description="提交一个 OpenCode SDK 后台任务到 MCP 队列；最多 20 个活跃任务，后台自动轮询并在停滞时补继续执行。",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "title": {"type": "string", "default": ""},
                    "host": {"type": "string", "default": DEFAULT_HOST},
                    "port": {"type": "number", "default": DEFAULT_PORT},
                    "session_id": {"type": "string", "default": ""},
                    "agent": {"type": "string", "default": ""},
                    "username": {"type": "string", "default": ""},
                    "password": {"type": "string", "default": ""},
                    "poll_seconds": {"type": "number", "default": 10},
                    "stall_seconds": {"type": "number", "default": 120},
                    "max_continue": {"type": "number", "default": 3},
                    "max_runtime_seconds": {"type": "number", "default": 7200},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="opencode_sdk_job_dispatch_letter",
            description="把投递箱任务信提交到 OpenCode SDK 后台队列；返回 job_id，可用 status/list 查询。",
            inputSchema={
                "type": "object",
                "properties": {
                    "letter": {"type": "string", "description": "投递箱文件名或绝对路径"},
                    "title": {"type": "string", "default": ""},
                    "host": {"type": "string", "default": DEFAULT_HOST},
                    "port": {"type": "number", "default": DEFAULT_PORT},
                    "session_id": {"type": "string", "default": ""},
                    "agent": {"type": "string", "default": ""},
                    "username": {"type": "string", "default": ""},
                    "password": {"type": "string", "default": ""},
                    "poll_seconds": {"type": "number", "default": 10},
                    "stall_seconds": {"type": "number", "default": 120},
                    "max_continue": {"type": "number", "default": 3},
                    "max_runtime_seconds": {"type": "number", "default": 7200},
                },
                "required": ["letter"],
            },
        ),
        Tool(
            name="opencode_sdk_job_status",
            description="查询一个 OpenCode SDK 后台任务状态；会优先通过 SDK messages 刷新结果，不需要看日志。",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "refresh": {"type": "boolean", "default": True},
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="opencode_sdk_job_list",
            description="列出 OpenCode SDK 后台队列任务，支持按状态过滤。",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "default": ""},
                    "limit": {"type": "number", "default": 50},
                },
            },
        ),
        Tool(
            name="opencode_sdk_job_continue",
            description="手动给某个 OpenCode SDK 后台任务补一句继续执行，并重新纳入后台监控。",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "prompt": {"type": "string", "default": ""},
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="opencode_sdk_job_notifications",
            description="查看 OpenCode SDK 后台任务终态通知收件箱；job 完成/失败/超时后会落盘，供 Codex 主线程轮询接手。",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "default": "", "description": "可选过滤 completed/failed/stalled/timeout"},
                    "unread_only": {"type": "boolean", "default": True},
                    "limit": {"type": "number", "default": 20},
                    "mark_read": {"type": "boolean", "default": False},
                    "acknowledged_by": {"type": "string", "default": "codex"},
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    host = arguments.get("host", DEFAULT_HOST)
    port = int(arguments.get("port", DEFAULT_PORT))
    if name == "opencode_gateway_status":
        return json.dumps(gateway_status(repo_root, host=host, port=port), ensure_ascii=False, indent=2)
    if name == "opencode_gateway_start":
        return json.dumps(start_gateway(repo_root, host=host, port=port), ensure_ascii=False, indent=2)
    if name == "opencode_list_letters":
        return json.dumps(
            list_letters(
                repo_root,
                target_contains=arguments.get("target_contains", ""),
                limit=int(arguments.get("limit", 50)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_dispatch_letter":
        return json.dumps(
            dispatch_letter(
                repo_root,
                letter=arguments["letter"],
                host=host,
                port=port,
                title=arguments.get("title", ""),
                background=bool(arguments.get("background", True)),
                timeout_seconds=int(arguments.get("timeout_seconds", 1800)),
                dangerously_skip_permissions=bool(arguments.get("dangerously_skip_permissions", True)),
                use_proxy=bool(arguments.get("use_proxy", False)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_sdk_smoke":
        return json.dumps(
            sdk_smoke(
                repo_root,
                host=host,
                port=port,
                prompt=arguments.get("prompt", ""),
                title=arguments.get("title", ""),
                username=arguments.get("username", ""),
                password=arguments.get("password", ""),
                timeout_seconds=int(arguments.get("timeout_seconds", 1800)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_sdk_prompt":
        return json.dumps(
            sdk_prompt(
                repo_root,
                prompt=arguments["prompt"],
                host=host,
                port=port,
                title=arguments.get("title", ""),
                session_id=arguments.get("session_id", ""),
                agent=arguments.get("agent", ""),
                username=arguments.get("username", ""),
                password=arguments.get("password", ""),
                timeout_seconds=int(arguments.get("timeout_seconds", 1800)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_sdk_dispatch_letter":
        return json.dumps(
            sdk_dispatch_letter(
                repo_root,
                letter=arguments["letter"],
                host=host,
                port=port,
                title=arguments.get("title", ""),
                session_id=arguments.get("session_id", ""),
                agent=arguments.get("agent", ""),
                username=arguments.get("username", ""),
                password=arguments.get("password", ""),
                timeout_seconds=int(arguments.get("timeout_seconds", 1800)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_sdk_messages":
        return json.dumps(
            sdk_messages(
                repo_root,
                session_id=arguments["session_id"],
                host=host,
                port=port,
                limit=int(arguments.get("limit", 50)),
                username=arguments.get("username", ""),
                password=arguments.get("password", ""),
                timeout_seconds=int(arguments.get("timeout_seconds", 60)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_sdk_job_submit":
        return json.dumps(
            opencode_queue.submit_job(
                repo_root,
                payload={
                    "action": "prompt_async",
                    "prompt": arguments["prompt"],
                    "title": arguments.get("title", ""),
                },
                title=arguments.get("title", "") or "opencode-sdk-job",
                job_type="prompt",
                host=host,
                port=port,
                session_id=arguments.get("session_id", ""),
                agent=arguments.get("agent", ""),
                username=arguments.get("username", ""),
                password=arguments.get("password", ""),
                poll_seconds=int(arguments.get("poll_seconds", 10)),
                stall_seconds=int(arguments.get("stall_seconds", 120)),
                max_continue=int(arguments.get("max_continue", 3)),
                max_runtime_seconds=int(arguments.get("max_runtime_seconds", 7200)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_sdk_job_dispatch_letter":
        letter_path = _resolve_letter(repo_root, arguments["letter"])
        return json.dumps(
            opencode_queue.submit_job(
                repo_root,
                payload={
                    "action": "dispatch_letter_async",
                    "letter_path": str(letter_path),
                    "letter_title": letter_path.stem,
                    "title": arguments.get("title", "") or letter_path.stem,
                },
                title=arguments.get("title", "") or letter_path.stem,
                job_type="letter",
                host=host,
                port=port,
                session_id=arguments.get("session_id", ""),
                agent=arguments.get("agent", ""),
                username=arguments.get("username", ""),
                password=arguments.get("password", ""),
                poll_seconds=int(arguments.get("poll_seconds", 10)),
                stall_seconds=int(arguments.get("stall_seconds", 120)),
                max_continue=int(arguments.get("max_continue", 3)),
                max_runtime_seconds=int(arguments.get("max_runtime_seconds", 7200)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_sdk_job_status":
        return json.dumps(
            opencode_queue.get_job(
                repo_root,
                arguments["job_id"],
                refresh=bool(arguments.get("refresh", True)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_sdk_job_list":
        return json.dumps(
            opencode_queue.list_jobs(
                repo_root,
                status=arguments.get("status", ""),
                limit=int(arguments.get("limit", 50)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_sdk_job_continue":
        return json.dumps(
            opencode_queue.continue_job(
                repo_root,
                arguments["job_id"],
                prompt=arguments.get("prompt", "") or opencode_queue.CONTINUE_PROMPT,
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "opencode_sdk_job_notifications":
        return json.dumps(
            opencode_queue.list_notifications(
                repo_root,
                status=arguments.get("status", ""),
                unread_only=bool(arguments.get("unread_only", True)),
                limit=int(arguments.get("limit", 20)),
                mark_read=bool(arguments.get("mark_read", False)),
                acknowledged_by=arguments.get("acknowledged_by", "codex"),
            ),
            ensure_ascii=False,
            indent=2,
        )
    raise ValueError(f"未知 opencode 工具: {name}")
