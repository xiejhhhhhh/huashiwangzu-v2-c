"""Shared subprocess helpers for project toolkit commands."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


def popen_process_group(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    stdout: Any = subprocess.PIPE,
    stderr: Any = subprocess.PIPE,
    text: bool = True,
) -> subprocess.Popen:
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=stdout,
        stderr=stderr,
        text=text,
        start_new_session=True,
    )


async def create_subprocess_exec_group(
    *cmd: str,
    cwd: Path,
    env: dict[str, str] | None = None,
    stdout: Any = asyncio.subprocess.PIPE,
    stderr: Any = asyncio.subprocess.PIPE,
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=stdout,
        stderr=stderr,
        cwd=str(cwd),
        env=env,
        start_new_session=True,
    )


def _kill_process_group(pid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return
    except PermissionError:
        return
    except OSError:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return


async def terminate_process_tree(proc: asyncio.subprocess.Process, *, grace_seconds: float = 5.0) -> None:
    if proc.returncode is not None:
        return
    pid = getattr(proc, "pid", None)
    if isinstance(pid, int) and pid > 0:
        _kill_process_group(pid, signal.SIGTERM)
    else:
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
    except asyncio.TimeoutError:
        if isinstance(pid, int) and pid > 0:
            _kill_process_group(pid, signal.SIGKILL)
        else:
            proc.kill()
        await proc.wait()


def terminate_popen_tree(proc: subprocess.Popen, *, grace_seconds: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    pid = proc.pid
    if pid:
        _kill_process_group(pid, signal.SIGTERM)
    else:
        proc.terminate()
    deadline = time.monotonic() + grace_seconds
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if proc.poll() is None:
        if pid:
            _kill_process_group(pid, signal.SIGKILL)
        else:
            proc.kill()
        proc.wait()
