"""Memory embedding service — bge-m3 embedding computation and vector storage.

Extracted from router.py to follow Router → Service → Model layering.
"""
import logging

from huashiwangzu_modules.memory.models import MemoryChunk, MemoryRecord
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.memory").getChild("embedding_service")


async def _compute_embedding(text: str) -> list[float] | None:
    """Compute embedding via framework model_services. Returns None on failure."""
    try:
        from app.services.model_services import get_embedding
        return await get_embedding(text[:2048])
    except Exception as e:
        logger.warning("Embedding computation failed: %s", e)
        return None


async def _update_embedding_sql(db, memory_id: int, vec_literal: str) -> None:
    """Shared helper: update embedding vector using parameterized SQL."""
    sql = "UPDATE memory_records SET embedding = CAST(:embedding AS vector(1024)) WHERE id = :id"
    await db.execute(text(sql), {"embedding": vec_literal, "id": memory_id})
    await db.commit()


async def backfill_missing_record_embeddings(
    db: AsyncSession,
    *,
    owner_id: int | None = None,
    limit: int = 20,
    dry_run: bool = True,
    run_dream: bool = False,
) -> dict:
    """Safely backfill missing memory record embeddings.

    The function intentionally processes records one by one through the normal
    embedding helper and storage helper. Dry-run mode only reports candidates.
    """
    safe_limit = max(1, min(int(limit or 20), 100))
    owner_filter = MemoryRecord.owner_id == owner_id if owner_id else None

    total_stmt = select(func.count()).select_from(MemoryRecord)
    with_embedding_stmt = select(func.count()).select_from(MemoryRecord).where(MemoryRecord.embedding.is_not(None))
    missing_stmt = select(func.count()).select_from(MemoryRecord).where(MemoryRecord.embedding.is_(None))
    candidate_stmt = (
        select(MemoryRecord)
        .where(MemoryRecord.embedding.is_(None))
        .order_by(MemoryRecord.created_at.asc(), MemoryRecord.id.asc())
        .limit(safe_limit)
    )
    if owner_filter is not None:
        total_stmt = total_stmt.where(owner_filter)
        with_embedding_stmt = with_embedding_stmt.where(owner_filter)
        missing_stmt = missing_stmt.where(owner_filter)
        candidate_stmt = candidate_stmt.where(owner_filter)

    total = await db.scalar(total_stmt) or 0
    with_embedding = await db.scalar(with_embedding_stmt) or 0
    missing = await db.scalar(missing_stmt) or 0
    rows = (await db.execute(candidate_stmt)).scalars().all()

    result: dict = {
        "dry_run": dry_run,
        "owner_id": owner_id,
        "limit": safe_limit,
        "total": total,
        "with_embedding": with_embedding,
        "missing": missing,
        "selected_count": len(rows),
        "processed": 0,
        "updated": 0,
        "failed": 0,
        "failures": [],
        "sample_ids": [row.id for row in rows[:10]],
        "dream": None,
        "dream_failures": [],
        "diagnostic": None,
    }
    if dry_run or not rows:
        result["diagnostic"] = "dry_run_only" if dry_run else "no_missing_embeddings_selected"
        return result

    updated_owner_ids: set[int] = set()
    for memory in rows:
        result["processed"] += 1
        try:
            vec = await _compute_embedding(memory.text)
            if not vec:
                result["failed"] += 1
                result["failures"].append({"id": memory.id, "reason": "embedding_service_returned_empty"})
                continue
            vec_literal = "[" + ",".join(str(v) for v in vec) + "]"
            await _update_embedding_sql(db, memory.id, vec_literal)
            result["updated"] += 1
            updated_owner_ids.add(memory.owner_id)
        except Exception as exc:
            await db.rollback()
            logger.warning("Memory embedding backfill failed for %s: %s", memory.id, exc)
            result["failed"] += 1
            result["failures"].append({"id": memory.id, "reason": str(exc)[:300]})

    if run_dream and result["updated"] > 0:
        from . import memory_service

        dream_reports = {}
        for target_owner_id in sorted(updated_owner_ids):
            if owner_id and target_owner_id != owner_id:
                continue
            try:
                dream_reports[str(target_owner_id)] = await memory_service._do_dream(db, target_owner_id)
            except Exception as exc:
                await db.rollback()
                logger.warning("Memory dream backfill follow-up failed for owner %s: %s", target_owner_id, exc)
                result["dream_failures"].append({"owner_id": target_owner_id, "reason": str(exc)[:300]})
        result["dream"] = dream_reports

    if result["failed"]:
        result["diagnostic"] = "completed_with_failures"
    elif result["dream_failures"]:
        result["diagnostic"] = "completed_with_dream_failures"
    else:
        result["diagnostic"] = "completed"
    return result


async def backfill_missing_chunk_embeddings(
    db: AsyncSession,
    *,
    owner_id: int | None = None,
    limit: int = 20,
    dry_run: bool = True,
) -> dict:
    """Safely backfill missing memory_chunk embeddings.

    Processes chunk text through the normal embedding pipeline.
    Dry-run mode only reports candidates.
    """
    safe_limit = max(1, min(int(limit or 20), 100))

    total_stmt = select(func.count()).select_from(MemoryChunk)
    with_embedding_stmt = select(func.count()).select_from(MemoryChunk).where(MemoryChunk.embedding.is_not(None))
    missing_stmt = select(func.count()).select_from(MemoryChunk).where(MemoryChunk.embedding.is_(None))
    candidate_stmt = (
        select(MemoryChunk)
        .where(MemoryChunk.embedding.is_(None))
        .order_by(MemoryChunk.created_at.asc(), MemoryChunk.id.asc())
        .limit(safe_limit)
    )
    if owner_id is not None:
        total_stmt = total_stmt.where(MemoryChunk.owner_id == owner_id)
        with_embedding_stmt = with_embedding_stmt.where(MemoryChunk.owner_id == owner_id)
        missing_stmt = missing_stmt.where(MemoryChunk.owner_id == owner_id)
        candidate_stmt = candidate_stmt.where(MemoryChunk.owner_id == owner_id)

    total = await db.scalar(total_stmt) or 0
    with_embedding = await db.scalar(with_embedding_stmt) or 0
    missing = await db.scalar(missing_stmt) or 0
    rows = (await db.execute(candidate_stmt)).scalars().all()

    result: dict = {
        "dry_run": dry_run,
        "owner_id": owner_id,
        "limit": safe_limit,
        "total": total,
        "with_embedding": with_embedding,
        "missing": missing,
        "selected_count": len(rows),
        "processed": 0,
        "updated": 0,
        "failed": 0,
        "failures": [],
        "diagnostic": None,
    }
    if dry_run or not rows:
        result["diagnostic"] = "dry_run_only" if dry_run else "no_missing_embeddings_selected"
        return result

    for chunk in rows:
        result["processed"] += 1
        try:
            vec = await _compute_embedding(chunk.text)
            if not vec:
                result["failed"] += 1
                result["failures"].append({"id": chunk.id, "reason": "embedding_service_returned_empty"})
                continue
            vec_literal = "[" + ",".join(str(v) for v in vec) + "]"
            sql = "UPDATE memory_chunks SET embedding = CAST(:embedding AS vector(1024)) WHERE id = :id"
            await db.execute(text(sql), {"embedding": vec_literal, "id": chunk.id})
            result["updated"] += 1
        except Exception as exc:
            await db.rollback()
            logger.warning("Chunk embedding backfill failed for %s: %s", chunk.id, exc)
            result["failed"] += 1
            result["failures"].append({"id": chunk.id, "reason": str(exc)[:300]})

    await db.commit()

    if result["failed"]:
        result["diagnostic"] = "completed_with_failures"
    else:
        result["diagnostic"] = "completed"
    return result
