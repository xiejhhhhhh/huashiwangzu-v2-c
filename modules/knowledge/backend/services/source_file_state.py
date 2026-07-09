"""Source-file lifecycle helpers for the knowledge pipeline."""
import os
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.core.exceptions import NotFound
from app.models.file import File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

NON_CONTENT_FILE_REASONS = {
    "non_content_appledouble_sidecar",
    "non_content_office_lock_file",
    "non_content_windows_recycle_metadata_file",
}


@dataclass(frozen=True)
class SourceFileAvailability:
    available: bool
    reason: str = ""
    storage_path: str | None = None
    physical_path: str | None = None


def classify_non_content_file(file: File | None, physical_path: str | None = None) -> str | None:
    """Return a terminal skip reason for filesystem sidecars and editor lock files."""
    if not file:
        return None
    name = str(getattr(file, "name", "") or getattr(file, "filename", "") or "").strip()
    storage_name = Path(str(getattr(file, "storage_path", "") or "")).name
    candidates = [value for value in (name, storage_name) if value]
    if any(candidate.startswith("~$") for candidate in candidates):
        return "non_content_office_lock_file"
    if any(candidate.startswith("._") for candidate in candidates):
        return "non_content_appledouble_sidecar"
    if any(candidate.startswith("$I") and len(candidate) >= 3 for candidate in candidates):
        return "non_content_windows_recycle_metadata_file"
    if physical_path:
        try:
            with Path(physical_path).open("rb") as fh:
                header = fh.read(18)
            if header.startswith(b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X"):
                return "non_content_appledouble_sidecar"
        except OSError:
            return None
    return None


def classify_file_availability(file: File | None) -> SourceFileAvailability:
    """Classify both database lifecycle and on-disk source availability."""
    if not file:
        return SourceFileAvailability(False, "source_file_missing")
    storage_path = str(file.storage_path or "").strip()
    if file.deleted:
        return SourceFileAvailability(False, "source_file_deleted", storage_path=storage_path or None)
    if not storage_path:
        return SourceFileAvailability(False, "source_storage_path_missing")

    upload_root = Path(get_settings().UPLOAD_DIR).resolve()
    try:
        full_path = (upload_root / storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
            return SourceFileAvailability(False, "source_path_unsafe", storage_path=storage_path)
        if not full_path.exists() or not full_path.is_file():
            return SourceFileAvailability(
                False,
                "source_file_physical_missing",
                storage_path=storage_path,
                physical_path=str(full_path),
            )
    except (OSError, ValueError):
        return SourceFileAvailability(False, "source_path_unsafe", storage_path=storage_path)

    return SourceFileAvailability(
        True,
        "",
        storage_path=storage_path,
        physical_path=str(full_path),
    )


class SourceFileUnavailable(Exception):
    """Raised when a source file was intentionally removed from the active file tree."""

    def __init__(self, file_id: int, reason: str):
        self.file_id = file_id
        self.reason = reason
        super().__init__(f"Source file {file_id} unavailable: {reason}")


async def get_source_file_availability(
    db: AsyncSession,
    file_id: int,
) -> SourceFileAvailability:
    """Classify lifecycle and physical absence without reading file contents."""
    result = await db.execute(
        select(File)
        .where(File.id == file_id)
        .execution_options(populate_existing=True)
    )
    file = result.scalar_one_or_none()
    return classify_file_availability(file)


async def raise_if_source_unavailable(db: AsyncSession, file_id: int) -> None:
    state = await get_source_file_availability(db, file_id)
    if not state.available:
        raise SourceFileUnavailable(file_id, state.reason)


async def get_live_document_or_raise(db: AsyncSession, document_id: int, owner_id: int) -> dict:
    """Return a visible knowledge document only when its source file is still live."""
    from .document_service import get_document

    doc = await get_document(db, document_id, owner_id)
    state = await get_source_file_availability(db, int(doc.get("file_id") or 0))
    if not state.available:
        raise NotFound(f"Document source file unavailable: {state.reason}")
    doc["source_available"] = True
    doc["source_state"] = "available"
    return doc
