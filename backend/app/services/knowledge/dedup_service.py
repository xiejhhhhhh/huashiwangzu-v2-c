import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Chunk, Catalog

logger = logging.getLogger("dedup_service")


class DedupService:

    @staticmethod
    async def is_duplicate_chunk(
        db: AsyncSession, content_hash: str, catalog_id: int | None = None
    ) -> bool:
        stmt = select(func.count(Chunk.id)).where(
            Chunk.content_hash == content_hash
        )
        if catalog_id is not None:
            stmt = stmt.where(Chunk.catalog_id != catalog_id)
        result = await db.execute(stmt)
        count = result.scalar()
        return count > 0

    @staticmethod
    async def find_duplicates_across_files(
        db: AsyncSession, catalog_id: int
    ) -> list[dict]:
        subq = (
            select(Chunk.content_hash, func.count(Chunk.id).label("cnt"))
            .where(Chunk.catalog_id != catalog_id)
            .group_by(Chunk.content_hash)
            .subquery()
        )
        stmt = (
            select(Chunk, subq.c.cnt)
            .join(subq, Chunk.content_hash == subq.c.content_hash)
            .where(Chunk.catalog_id == catalog_id)
            .order_by(Chunk.page_num, Chunk.char_offset)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "chunk_id": row.Chunk.id,
                "page_num": row.Chunk.page_num,
                "content_hash": row.Chunk.content_hash,
                "same_in_other_files": row.cnt,
                "content_preview": row.Chunk.content[:80],
            }
            for row in rows
        ]

    @staticmethod
    async def check_file_hash_exists(
        db: AsyncSession, file_hash: str
    ) -> bool:
        result = await db.execute(
            select(Catalog).where(Catalog.file_hash == file_hash)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def log_duplicate_skip(
        chunk_preview: str, content_hash: str, existing_catalog_id: int
    ):
        logger.info(
            "Skipped duplicate chunk | hash=%s | preview=%s | existing_in_catalog=%s",
            content_hash, chunk_preview[:60], existing_catalog_id,
        )
