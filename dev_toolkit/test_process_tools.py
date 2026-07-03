"""Tests for process_tools signal fallback behavior."""

from __future__ import annotations

import signal

from dev_toolkit import process_tools


def test_kill_process_group_uses_killpg_success(monkeypatch) -> None:
    calls: list[tuple[str, int, signal.Signals]] = []

    def fake_killpg(pid: int, sig: signal.Signals) -> None:
        calls.append(("killpg", pid, sig))

    def forbidden_kill(_pid: int, _sig: signal.Signals) -> None:
        raise AssertionError("os.kill should not run when killpg succeeds")

    monkeypatch.setattr(process_tools.os, "killpg", fake_killpg)
    monkeypatch.setattr(process_tools.os, "kill", forbidden_kill)

    process_tools._kill_process_group(123, signal.SIGTERM)

    assert calls == [("killpg", 123, signal.SIGTERM)]


def test_kill_process_group_ignores_missing_process_group(monkeypatch) -> None:
    kill_calls: list[tuple[int, signal.Signals]] = []

    def fake_killpg(_pid: int, _sig: signal.Signals) -> None:
        raise ProcessLookupError

    def fake_kill(pid: int, sig: signal.Signals) -> None:
        kill_calls.append((pid, sig))

    monkeypatch.setattr(process_tools.os, "killpg", fake_killpg)
    monkeypatch.setattr(process_tools.os, "kill", fake_kill)

    process_tools._kill_process_group(123, signal.SIGTERM)

    assert kill_calls == []


def test_kill_process_group_falls_back_to_process_kill_on_os_error(monkeypatch) -> None:
    calls: list[tuple[str, int, signal.Signals]] = []

    def fake_killpg(pid: int, sig: signal.Signals) -> None:
        calls.append(("killpg", pid, sig))
        raise OSError("process group unavailable")

    def fake_kill(pid: int, sig: signal.Signals) -> None:
        calls.append(("kill", pid, sig))

    monkeypatch.setattr(process_tools.os, "killpg", fake_killpg)
    monkeypatch.setattr(process_tools.os, "kill", fake_kill)

    process_tools._kill_process_group(123, signal.SIGKILL)

    assert calls == [
        ("killpg", 123, signal.SIGKILL),
        ("kill", 123, signal.SIGKILL),
    ]


def test_terminate_popen_tree_returns_without_killing_exited_process(monkeypatch) -> None:
    class ExitedProcess:
        pid = 123

        def poll(self) -> int:
            return 0

        def terminate(self) -> None:
            raise AssertionError("terminate should not run for an exited process")

        def kill(self) -> None:
            raise AssertionError("kill should not run for an exited process")

        def wait(self) -> int:
            raise AssertionError("wait should not run for an exited process")

    kill_group_calls: list[tuple[int, signal.Signals]] = []

    def fake_kill_process_group(pid: int, sig: signal.Signals) -> None:
        kill_group_calls.append((pid, sig))

    monkeypatch.setattr(process_tools, "_kill_process_group", fake_kill_process_group)

    process_tools.terminate_popen_tree(ExitedProcess())

    assert kill_group_calls == []
