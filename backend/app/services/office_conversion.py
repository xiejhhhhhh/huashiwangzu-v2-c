"""Shared LibreOffice conversion helpers for Office-capable modules."""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

SUPPORTED_FORMATS = {
    "pdf", "docx", "pptx", "xlsx", "odt", "ods", "odp",
    "html", "rtf", "txt", "csv", "png", "jpg", "tiff",
}


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
    timeout_seconds: int = 180,
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

    profile_dir = tempfile.mkdtemp(prefix="lo_profile_")
    try:
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
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    finally:
        await asyncio.to_thread(shutil.rmtree, profile_dir, True)
    if proc.returncode != 0:
        output = "\n".join(
            part.decode("utf-8", errors="replace").strip()
            for part in (stdout, stderr)
            if part
        ).strip()
        raise RuntimeError(f"LibreOffice conversion failed (exit={proc.returncode}): {output}")

    output_path = outdir / f"{source.stem}.{target_format}"
    if not output_path.exists():
        matches = sorted(outdir.glob(f"{source.stem}.*"))
        for candidate in matches:
            if candidate.suffix.lower().lstrip(".") == target_format:
                return str(candidate)
        raise RuntimeError(f"Conversion completed but output file not found at: {output_path}")
    return str(output_path)


async def convert_by_file_id(source_path: str | Path, target_format: str) -> tuple[str, bytes]:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="office_conv_") as tmpdir:
        output_path = Path(await convert_file(source_path, target_format, tmpdir))
        content = output_path.read_bytes()
        if not content:
            raise RuntimeError(f"Conversion produced an empty output file: {output_path.name}")
        return output_path.name, content
