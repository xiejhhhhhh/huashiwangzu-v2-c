from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services import office_conversion


def _settings(
    *,
    max_concurrent: int = 2,
    timeout: float = 1,
    grace: float = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        OFFICE_CONVERSION_MAX_CONCURRENT=max_concurrent,
        OFFICE_CONVERSION_TIMEOUT_SECONDS=timeout,
        OFFICE_CONVERSION_TERMINATE_GRACE_SECONDS=grace,
    )


@pytest.mark.asyncio
async def test_convert_file_timeout_terminates_process_with_clear_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "legacy.doc"
    source.write_bytes(b"legacy office bytes")

    class SlowProcess:
        pid = None
        returncode = None

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(30)
            return b"", b""

    process = SlowProcess()
    terminated: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args: object, **kwargs: object) -> SlowProcess:
        return process

    async def fake_terminate(proc: object, *, grace_seconds: float) -> None:
        terminated["proc"] = proc
        terminated["grace_seconds"] = grace_seconds

    monkeypatch.setattr(office_conversion, "check_libreoffice", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(office_conversion, "get_settings", lambda: _settings(timeout=0.01, grace=1.25))
    monkeypatch.setattr(office_conversion.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(office_conversion, "_terminate_process", fake_terminate)

    with pytest.raises(
        office_conversion.OfficeConversionTimeoutError,
        match=r"LibreOffice conversion timed out after 0\.01s: legacy\.doc -> pdf",
    ):
        await office_conversion.convert_file(source, "pdf", tmp_path)

    assert terminated == {"proc": process, "grace_seconds": 1.25}


@pytest.mark.asyncio
async def test_convert_file_nonzero_exit_without_output_has_diagnostic_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "broken.xls"
    source.write_bytes(b"broken office bytes")

    class FailedProcess:
        pid = None
        returncode = 1

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b""

    async def fake_create_subprocess_exec(*args: object, **kwargs: object) -> FailedProcess:
        return FailedProcess()

    monkeypatch.setattr(office_conversion, "check_libreoffice", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(office_conversion, "get_settings", lambda: _settings())
    monkeypatch.setattr(office_conversion.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(
        RuntimeError,
        match=r"LibreOffice conversion failed \(exit=1\): \(no LibreOffice output\)",
    ):
        await office_conversion.convert_file(source, "xlsx", tmp_path)


@pytest.mark.asyncio
async def test_terminate_process_escalates_from_term_to_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HungProcess:
        pid = None
        returncode = None
        wait_calls = 0

        async def wait(self) -> None:
            self.wait_calls += 1
            if self.wait_calls == 1:
                await asyncio.sleep(30)
                return
            self.returncode = -9

    process = HungProcess()
    sent_signals: list[signal.Signals] = []

    def fake_send_signal(proc: object, sig: signal.Signals) -> None:
        assert proc is process
        sent_signals.append(sig)

    monkeypatch.setattr(office_conversion, "_send_signal", fake_send_signal)

    await office_conversion._terminate_process(process, grace_seconds=0.01)  # type: ignore[arg-type]

    assert sent_signals == [signal.SIGTERM, office_conversion._kill_signal()]
    assert process.returncode == -9


@pytest.mark.asyncio
async def test_conversion_semaphore_reuses_loop_and_rebuilds_on_limit_change() -> None:
    first = office_conversion._conversion_semaphore(2)
    second = office_conversion._conversion_semaphore(2)
    third = office_conversion._conversion_semaphore(3)

    assert first is second
    assert third is not first
