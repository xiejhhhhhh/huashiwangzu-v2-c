"""Rebuild stored chunks for an already parsed knowledge document."""

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ir_models import from_legacy_blocks
from ..models import KbChunk, KbDocument
from .chunking_service import chunk_document
from .search_service import get_document_chunks
from .source_file_state import get_live_document_or_raise


def _chunk_to_legacy_block(chunk: dict) -> dict:
    block_type = "heading" if chunk.get("block_type", "段落") in ("标题",) else "paragraph"
    return {
        "type": block_type,
        "text": chunk.get("text", ""),
        "page": chunk.get("page"),
    }


async def rebuild_document_chunks(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    strategy: str,
    max_chars: int,
) -> dict:
    """Re-chunk a parsed document using its currently stored chunks as source."""
    await get_live_document_or_raise(db, document_id, owner_id)

    current_chunks = await get_document_chunks(db, document_id, owner_id=owner_id)
    ir_blocks = [_chunk_to_legacy_block(chunk) for chunk in current_chunks]
    if not ir_blocks:
        return {"error": "No chunks to re-chunk", "chunks": 0}

    doc_ir = from_legacy_blocks(file_id=0, fmt="", blocks=ir_blocks)

    await db.execute(sa_delete(KbChunk).where(KbChunk.document_id == document_id))
    await db.commit()

    new_chunks = chunk_document(doc_ir, strategy=strategy, max_chars=max_chars)
    stored = 0
    for chunk_index, chunk in enumerate(new_chunks):
        record = KbChunk(
            document_id=document_id,
            owner_id=owner_id,
            page=chunk.get("page"),
            chunk_index=chunk_index,
            block_type=chunk.get("block_type", "段落"),
            text=chunk.get("text", ""),
            keywords="",
        )
        db.add(record)
        stored += 1
        if stored % 50 == 0:
            await db.flush()
    await db.commit()

    result = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
    doc = result.scalar_one_or_none()
    if doc:
        doc.total_chunks = stored

    await db.commit()
    return {"chunks": stored, "strategy": strategy}
