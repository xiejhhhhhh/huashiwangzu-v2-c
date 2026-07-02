"""Source-file lifecycle helpers for the knowledge pipeline."""
from dataclasses import dataclass

from app.core.exceptions import NotFound
from app.models.file import File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SourceFileAvailability:
    available: bool
    reason: str = ""


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
    """Classify lifecycle absence without reading file contents from disk."""
    result = await db.execute(
        select(File)
        .where(File.id == file_id)
        .execution_options(populate_existing=True)
    )
    file = result.scalar_one_or_none()
    if not file:
        return SourceFileAvailability(False, "source_file_missing")
    if file.deleted:
        return SourceFileAvailability(False, "source_file_deleted")
    return SourceFileAvailability(True, "")


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
