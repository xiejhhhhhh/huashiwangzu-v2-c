"""Shared LibreOffice conversion helpers for Office-capable modules."""
from __future__ import annotations

import asyncio
import os
import shutil
import signal
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from weakref import WeakKeyDictionary

from app.config import BACKEND_DIR, get_settings

SUPPORTED_FORMATS = {
    "pdf", "docx", "pptx", "xlsx", "odt", "ods", "odp",
    "html", "rtf", "txt", "csv", "png", "jpg", "tiff",
}
_SEMAPHORES: WeakKeyDictionary[asyncio.AbstractEventLoop, tuple[int, asyncio.Semaphore]] = WeakKeyDictionary()


class OfficeConversionTimeoutError(TimeoutError):
    """Raised when LibreOffice conversion exceeds the configured timeout."""


@dataclass
class _GlobalConversionSlot:
    path: Path
    fd: int

    def release(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def check_libreoffice() -> str | None:
    """Return a usable LibreOffice/soffice binary path."""
    env_path = os.getenv("LIBREOFFICE_BIN") or os.getenv("SOFFICE_BIN")
    candidates = [
        env_path,
        "soffice",
        "libreoffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/soffice"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if os.sep not in candidate else candidate
        if resolved and Path(resolved).exists():
            return str(resolved)
    return None


def get_install_instructions() -> str:
    return (
        "LibreOffice is required for format conversion.\n"
        "  macOS: brew install --cask libreoffice\n"
        "  Ubuntu/Debian: sudo apt install libreoffice\n"
        "  CentOS/RHEL: sudo yum install libreoffice\n"
        "  Windows: Download from https://www.libreoffice.org/download/"
    )


async def convert_file(
    source_path: str | Path,
    target_format: str,
    output_dir: str | Path | None = None,
    timeout_seconds: int | None = None,
) -> str:
    target_format = target_format.lower().lstrip(".")
    if target_format not in SUPPORTED_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_FORMATS))
        raise ValueError(f"Unsupported target format: {target_format}. Supported: {supported}")

    soffice = check_libreoffice()
    if not soffice:
        raise RuntimeError("LibreOffice is not installed. Cannot perform conversion.\n" + get_install_instructions())

    source = Path(source_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    outdir = Path(output_dir).resolve() if output_dir else source.parent
    outdir.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    effective_timeout = float(
        timeout_seconds if timeout_seconds is not None else settings.OFFICE_CONVERSION_TIMEOUT_SECONDS
    )
    max_concurrent = max(1, int(settings.OFFICE_CONVERSION_MAX_CONCURRENT))
    terminate_grace = max(0.5, float(settings.OFFICE_CONVERSION_TERMINATE_GRACE_SECONDS))
    stale_slot_seconds = max(300.0, effective_timeout + terminate_grace + 60.0)
    semaphore = _conversion_semaphore(max_concurrent)
    profile_dir = tempfile.mkdtemp(prefix="lo_profile_")
    proc: asyncio.subprocess.Process | None = None
    stdout = b""
    stderr = b""
    slot: _GlobalConversionSlot | None = None
    try:
        async with semaphore:
            try:
                slot = await _acquire_global_conversion_slot(
                    max_concurrent=max_concurrent,
                    stale_seconds=stale_slot_seconds,
                )
                cmd = [
                    soffice,
                    f"-env:UserInstallation={Path(profile_dir).resolve().as_uri()}",
                    "--headless",
                    "--convert-to",
                    target_format,
                    "--outdir",
                    str(outdir),
                    str(source),
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **_subprocess_group_kwargs(),
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=effective_timeout,
                    )
                except TimeoutError as exc:
                    await _terminate_process(proc, grace_seconds=terminate_grace)
                    raise OfficeConversionTimeoutError(
                        "LibreOffice conversion timed out "
                        f"after {effective_timeout:g}s: {source.name} -> {target_format}"
                    ) from exc
            finally:
                if slot is not None:
                    await asyncio.to_thread(slot.release)
    finally:
        await asyncio.to_thread(shutil.rmtree, profile_dir, True)
    if proc is None:
        raise RuntimeError("LibreOffice conversion process was not started")
    if proc.returncode != 0:
        output = _decode_process_output(stdout, stderr)
        raise RuntimeError(f"LibreOffice conversion failed (exit={proc.returncode}): {output}")

    output_path = outdir / f"{source.stem}.{target_format}"
    if not output_path.exists():
        matches = sorted(outdir.glob(f"{source.stem}.*"))
        for candidate in matches:
            if candidate.suffix.lower().lstrip(".") == target_format:
                return str(candidate)
        raise RuntimeError(f"Conversion completed but output file not found at: {output_path}")
    return str(output_path)


def _conversion_semaphore(max_concurrent: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    current = _SEMAPHORES.get(loop)
    if current is None or current[0] != max_concurrent:
        semaphore = asyncio.Semaphore(max_concurrent)
        _SEMAPHORES[loop] = (max_concurrent, semaphore)
        return semaphore
    return current[1]


async def _acquire_global_conversion_slot(
    *,
    max_concurrent: int,
    stale_seconds: float,
) -> _GlobalConversionSlot:
    lock_dir = _office_conversion_lock_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    while True:
        for slot_index in range(max(1, max_concurrent)):
            path = lock_dir / f"slot_{slot_index}.lock"
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except FileExistsError:
                _remove_stale_conversion_slot(path, stale_seconds=stale_seconds)
                continue
            os.write(fd, str(os.getpid()).encode("ascii"))
            return _GlobalConversionSlot(path=path, fd=fd)
        await asyncio.sleep(0.25)


def _office_conversion_lock_dir() -> Path:
    return BACKEND_DIR / "data" / "runtime" / "office_conversion_locks"


def _remove_stale_conversion_slot(path: Path, *, stale_seconds: float) -> None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return
    pid = _read_slot_pid(path)
    stale_by_age = (_now_monotonic_wall() - stat.st_mtime) > stale_seconds
    if pid is not None and _pid_is_alive(pid) and not stale_by_age:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _read_slot_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    try:
        pid = int(text)
    except ValueError:
        return None
    return pid if pid > 0 else None


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _now_monotonic_wall() -> float:
    return time.time()


def _subprocess_group_kwargs() -> dict[str, bool]:
    if os.name == "nt":
        return {}
    return {"start_new_session": True}


async def _terminate_process(
    proc: asyncio.subprocess.Process,
    *,
    grace_seconds: float,
) -> None:
    if proc.returncode is not None:
        return
    _send_signal(proc, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
        return
    except TimeoutError:
        pass
    if proc.returncode is None:
        _send_signal(proc, _kill_signal())
        await proc.wait()


def _send_signal(proc: asyncio.subprocess.Process, sig: signal.Signals) -> None:
    pid = getattr(proc, "pid", None)
    if os.name != "nt" and isinstance(pid, int) and pid > 0:
        try:
            os.killpg(os.getpgid(pid), sig)
            return
        except ProcessLookupError:
            return
        except OSError:
            pass
    try:
        if sig == _kill_signal():
            proc.kill()
        else:
            proc.terminate()
    except ProcessLookupError:
        return


def _kill_signal() -> signal.Signals:
    return getattr(signal, "SIGKILL", signal.SIGTERM)


def _decode_process_output(stdout: bytes, stderr: bytes) -> str:
    output = "\n".join(
        part.decode("utf-8", errors="replace").strip()
        for part in (stdout, stderr)
        if part
    ).strip()
    return output or "(no LibreOffice output)"


async def convert_by_file_id(source_path: str | Path, target_format: str) -> tuple[str, bytes]:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="office_conv_") as tmpdir:
        output_path = Path(await convert_file(source_path, target_format, tmpdir))
        content = output_path.read_bytes()
        if not content:
            raise RuntimeError(f"Conversion produced an empty output file: {output_path.name}")
        return output_path.name, content


async def convert_doc_to_text_with_textutil(
    source_path: str | Path,
    output_dir: str | Path | None = None,
    timeout_seconds: int | None = None,
) -> str:
    """Fallback DOC text extraction on macOS when LibreOffice cannot convert."""
    textutil = shutil.which("textutil")
    if not textutil:
        raise RuntimeError("macOS textutil is not available for DOC text fallback")

    source = Path(source_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    outdir = Path(output_dir).resolve() if output_dir else source.parent
    outdir.mkdir(parents=True, exist_ok=True)
    output_path = outdir / f"{source.stem}.txt"
    settings = get_settings()
    effective_timeout = float(
        timeout_seconds if timeout_seconds is not None else settings.OFFICE_CONVERSION_TIMEOUT_SECONDS
    )
    proc = await asyncio.create_subprocess_exec(
        textutil,
        "-convert",
        "txt",
        "-output",
        str(output_path),
        str(source),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **_subprocess_group_kwargs(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)
    except TimeoutError as exc:
        await _terminate_process(proc, grace_seconds=max(0.5, float(settings.OFFICE_CONVERSION_TERMINATE_GRACE_SECONDS)))
        raise OfficeConversionTimeoutError(
            "textutil DOC extraction timed out "
            f"after {effective_timeout:g}s: {source.name} -> txt"
        ) from exc

    if proc.returncode != 0:
        output = _decode_process_output(stdout, stderr)
        raise RuntimeError(f"textutil DOC extraction failed (exit={proc.returncode}): {output}")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        output = _decode_process_output(stdout, stderr)
        raise RuntimeError(f"textutil DOC extraction produced no text: {output}")
    return str(output_path)
