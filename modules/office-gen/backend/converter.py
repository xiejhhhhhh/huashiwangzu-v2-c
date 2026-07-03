"""Office format converter — uses LibreOffice headless for cross-format conversion.

Detects soffice/libreoffice availability and delegates conversion.
"""
import asyncio
import logging
import os
import shutil
import tempfile

logger = logging.getLogger("v2.office-gen").getChild("converter")

SUPPORTED_FORMATS = {
    "pdf", "docx", "pptx", "xlsx", "odt", "ods", "odp",
    "html", "rtf", "txt", "csv", "png", "jpg", "tiff",
}


def check_libreoffice() -> str | None:
    """Return the libreoffice/soffice binary path, or None if not found."""
    candidates = ["soffice", "libreoffice"]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return None


def get_install_instructions() -> str:
    """Return platform-specific installation instructions."""
    return (
        "LibreOffice is required for format conversion.\n"
        "  macOS: brew install --cask libreoffice\n"
        "  Ubuntu/Debian: sudo apt install libreoffice\n"
        "  CentOS/RHEL: sudo yum install libreoffice\n"
        "  Windows: Download from https://www.libreoffice.org/download/"
    )


async def convert_file(
    source_path: str,
    target_format: str,
    output_dir: str | None = None,
) -> str:
    """Convert a file using LibreOffice headless.

    Args:
        source_path: Absolute path to the source file.
        target_format: Target extension (e.g. 'pdf', 'docx', 'png').
        output_dir: Output directory (default: same dir as source).

    Returns:
        Path to the converted file.
    """
    target_format = target_format.lower().lstrip(".")
    if target_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported target format: {target_format}. "
                         f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}")

    soffice = check_libreoffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice is not installed. Cannot perform conversion.\n"
            + get_install_instructions()
        )

    source_path = os.path.abspath(source_path)
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source file not found: {source_path}")

    outdir = output_dir or os.path.dirname(source_path)
    os.makedirs(outdir, exist_ok=True)

    cmd = [
        soffice,
        "--headless",
        "--convert-to", target_format,
        "--outdir", outdir,
        source_path,
    ]

    logger.info("Running: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

    if proc.returncode != 0:
        error_msg = stderr.decode("utf-8", errors="replace") if stderr else ""
        raise RuntimeError(
            f"LibreOffice conversion failed (exit={proc.returncode}): {error_msg}"
        )

    # Find the output file with the expected extension
    basename = os.path.splitext(os.path.basename(source_path))[0]
    output_path = os.path.join(outdir, f"{basename}.{target_format}")

    if not os.path.exists(output_path):
        raise RuntimeError(
            f"Conversion completed but output file not found at: {output_path}"
        )

    logger.info("Conversion complete: %s -> %s", source_path, output_path)
    return output_path


async def convert_by_file_id(
    source_path: str,
    target_format: str,
) -> tuple[str, bytes]:
    """Convert file and return (filename, bytes) of the result."""
    with tempfile.TemporaryDirectory(prefix="office_conv_") as tmpdir:
        output_path = await convert_file(source_path, target_format, tmpdir)
        output_name = os.path.basename(output_path)
        with open(output_path, "rb") as f:
            content = f.read()
        if not content:
            raise RuntimeError(f"Conversion produced an empty output file: {output_name}")
    return output_name, content
