import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError

from huashiwangzu_modules.memory.models import MemoryRecord, MemoryLink, MemoryChunk
from huashiwangzu_modules.memory.init_db import run_init
from . import distill_service, embedding_service
from .embedding_service import _update_embedding_sql

logger = logging.getLogger("v2.memory").getChild("memory_service")

MEMORY_DREAM_SIMILARITY_MERGE = 0.92
MEMORY_DREAM_DECAY_DAYS = 30
MEMORY_CHUNK_MAX_CHARS = 900
MEMORY_CHUNK_OVERLAP_CHARS = 120


async def _ensure_init() -> None:
    await run_init()


def _parse_user_id(caller: str) -> int:
    if caller and caller.startswith("user:"):
        return int(caller.split(":", 1)[1])
    return 0


async def _update_embedding(memory_id: int, content: str) -> bool:
    try:
        from app.database import AsyncSessionLocal
        vec = await embedding_service._compute_embedding(content)
        if vec:
            async with AsyncSessionLocal() as db:
                vec_literal = "[" + ",".join(str(v) for v in vec) + "]"
                await _update_embedding_sql(db, memory_id, vec_literal)
            return True
    except Exception as e:
        logger.warning("Embedding update failed: %s", e)
    return False


async def _post_save_process(memory_id: int, content: str, source: str | None) -> None:
    try:
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            mem = await db.get(MemoryRecord, memory_id)
            if not mem:
                return
            # Embedding was already computed by the synchronous save path;
            # only compute here if the record has none (e.g. post-save from
            # background task where sync path was bypassed).
            if mem.embedding is None:
                vec = await embedding_service._compute_embedding(content)
                if vec:
                    vec_literal = "[" + ",".join(str(v) for v in vec) + "]"
                    await _update_embedding_sql(db, memory_id, vec_literal)
            distilled = await distill_service._distill_summary(content, source)
            update_parts = []
            params = {"id": memory_id}
            if distilled.get("summary"):
                update_parts.append("summary = :summary")
                params["summary"] = distilled["summary"]
            if distilled.get("memory_type"):
                update_parts.append("memory_type = :memory_type")
                params["memory_type"] = distilled["memory_type"]
            if distilled.get("keywords"):
                update_parts.append("keywords = :keywords")
                params["keywords"] = distilled["keywords"]
            if update_parts:
                sql = "UPDATE memory_records SET " + ", ".join(update_parts) + " WHERE id = :id"
                await db.execute(text(sql), params)
            await _refresh_chunks_for_memory(db, mem, content, source, distilled)
            await db.commit()
    except Exception as e:
        logger.warning("Post-save processing failed (non-fatal): %s", e)


def _split_memory_chunks(content: str) -> list[tuple[str, int, int]]:
    """Split memory text into paragraph-aware chunks with light overlap."""
    text_content = (content or "").strip()
    if not text_content:
        return []

    chunks: list[tuple[str, int, int]] = []
    start = 0
    text_len = len(text_content)

    while start < text_len:
        target_end = min(start + MEMORY_CHUNK_MAX_CHARS, text_len)
        end = target_end
        if target_end < text_len:
            paragraph_break = text_content.rfind("\n\n", start, target_end)
            sentence_break = max(
                text_content.rfind("。", start, target_end),
                text_content.rfind("！", start, target_end),
                text_content.rfind("？", start, target_end),
                text_content.rfind(".", start, target_end),
            )
            candidate = paragraph_break if paragraph_break > start + 200 else sentence_break
            if candidate > start + 200:
                end = candidate + 1

        chunk_text = text_content[start:end].strip()
        if chunk_text:
            chunks.append((chunk_text, start, end))
        if end >= text_len:
            break
        start = max(end - MEMORY_CHUNK_OVERLAP_CHARS, start + 1)

    return chunks


async def _refresh_chunks_for_memory(
    db: AsyncSession,
    memory: MemoryRecord,
    content: str,
    source: str | None,
    distilled: dict | None = None,
) -> None:
    """Rebuild chunk rows for a memory record.

    Chunk rows preserve raw text and provenance so vector recall can return
    the original paragraph instead of a detached embedding hit.
    """
    await db.execute(
        text("DELETE FROM memory_chunks WHERE memory_record_id = :id"),
        {"id": memory.id},
    )

    chunks = _split_memory_chunks(content)
    if not chunks:
        return

    summary = (distilled or {}).get("summary")
    for index, (chunk_text, start_char, end_char) in enumerate(chunks):
        vec = await embedding_service._compute_embedding(chunk_text)
        chunk = MemoryChunk(
            owner_id=memory.owner_id,
            memory_record_id=memory.id,
            chunk_index=index,
            text=chunk_text,
            summary=summary if index == 0 else None,
            embedding=vec,
            source=source or memory.source,
            conversation_id=memory.conversation_id,
            provenance=f"memory_record:{memory.id}#chunk:{index}",
            start_char=start_char,
            end_char=end_char,
            confidence=memory.confidence or 1.0,
        )
        db.add(chunk)


async def _do_fuse(db: AsyncSession, owner_id: int, query: str, ids: list[int]) -> dict:
    memories = []
    for mid in ids:
        m = await db.get(MemoryRecord, mid)
        if m and m.owner_id == owner_id:
            memories.append(m)
    if not memories:
        return {"fused": "", "source_ids": [], "note": "无有效记忆"}
    parts = []
    for i, m in enumerate(memories):
        label = m.summary or m.text[:100]
        parts.append(f"[{i+1}] {label}\n完整：{m.text[:500]}")
    combined = "\n\n".join(parts)
    prompt = (
        f"用户查询：{query}\n\n"
        f"相关记忆：\n{combined}\n\n"
        "请根据用户查询，将以上记忆融合成一段贴合查询的简报。"
        "要求：简洁、贴题、保留关键信息。直接输出融合后的文本，不要额外格式。"
    )
    content = await distill_service._call_cheap_model([
        {"role": "system", "content": "你是一个记忆融合助手，擅长将多条相关信息融合成贴合查询的简报。"},
        {"role": "user", "content": prompt},
    ])
    return {
        "fused": content or combined[:1000],
        "source_ids": [m.id for m in memories],
        "note": "融合成功" if content else "融合失败，降级为拼接摘要",
    }


async def _do_dream(db: AsyncSession, owner_id: int) -> dict:
    report = {"merged": 0, "links_created": 0, "decayed": 0}

    try:
        merge_sql = text("""
            SELECT a.id AS keep_id, b.id AS drop_id,
                   (1 - (a.embedding <=> b.embedding)) AS similarity
            FROM memory_records a
            JOIN memory_records b ON a.owner_id = b.owner_id AND a.id < b.id
            WHERE a.owner_id = :owner_id
              AND a.embedding IS NOT NULL
              AND b.embedding IS NOT NULL
              AND (1 - (a.embedding <=> b.embedding)) >= :threshold
            ORDER BY similarity DESC
        """)
        merge_candidates = await db.execute(merge_sql, {
            "owner_id": owner_id,
            "threshold": MEMORY_DREAM_SIMILARITY_MERGE,
        })
        merge_rows = merge_candidates.mappings().all()
        dropped = set()
        for row in merge_rows:
            keep_id = row["keep_id"]
            drop_id = row["drop_id"]
            if keep_id in dropped or drop_id in dropped:
                continue
            keep = await db.get(MemoryRecord, keep_id)
            drop = await db.get(MemoryRecord, drop_id)
            if not keep or not drop:
                continue
            new_conf = max(keep.confidence, drop.confidence)
            keep.confidence = new_conf
            keep.access_count = (keep.access_count or 0) + (drop.access_count or 0)
            await db.execute(
                text("DELETE FROM memory_links WHERE from_id = :id OR to_id = :id"),
                {"id": drop_id},
            )
            await db.delete(drop)
            dropped.add(drop_id)
            report["merged"] += 1
    except Exception as e:
        logger.warning("Dream merge failed: %s", e)

    try:
        link_sql = text("""
            SELECT a.id AS from_id, b.id AS to_id,
                   (1 - (a.embedding <=> b.embedding)) AS similarity
            FROM memory_records a
            JOIN memory_records b ON a.owner_id = b.owner_id AND a.id < b.id
            WHERE a.owner_id = :owner_id
              AND a.embedding IS NOT NULL
              AND b.embedding IS NOT NULL
              AND (1 - (a.embedding <=> b.embedding)) >= :threshold
              AND NOT EXISTS (
                  SELECT 1 FROM memory_links
                  WHERE (from_id = a.id AND to_id = b.id)
                     OR (from_id = b.id AND to_id = a.id)
              )
            ORDER BY similarity DESC
        """)
        link_candidates = await db.execute(link_sql, {
            "owner_id": owner_id,
            "threshold": 0.55,
        })
        for row in link_candidates.mappings().all():
            link = MemoryLink(
                from_id=row["from_id"],
                to_id=row["to_id"],
                relation="semantic_related",
                weight=row["similarity"],
                owner_id=owner_id,
            )
            db.add(link)
            report["links_created"] += 1
    except Exception as e:
        logger.warning("Dream link creation failed: %s", e)

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=MEMORY_DREAM_DECAY_DAYS)
        decay_result = await db.execute(
            text("""
                UPDATE memory_records
                SET recency_score = GREATEST(recency_score * 0.85, 0.1)
                WHERE owner_id = :owner_id
                  AND updated_at < :cutoff
                  AND access_count < 3
            """),
            {"owner_id": owner_id, "cutoff": cutoff},
        )
        report["decayed"] = decay_result.rowcount
    except Exception as e:
        logger.warning("Dream decay failed: %s", e)

    await db.commit()
    return report


async def _enqueue_post_save(memory_id: int, content: str, source: str | None) -> None:
    try:
        from app.models.system import SystemTaskQueue
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as eq_db:
            task = SystemTaskQueue(
                task_type="memory_post_save",
                parameters=json.dumps({
                    "memory_id": memory_id,
                    "content": content,
                    "source": source,
                }),
                status="pending",
                priority=0,
                module="memory",
            )
            eq_db.add(task)
            await eq_db.commit()
    except Exception as e:
        logger.warning("Post-save enqueue failed (non-fatal): %s", e)
