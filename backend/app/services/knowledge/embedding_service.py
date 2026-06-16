import logging

import httpx
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Chunk, ChunkVector, PageFusion
from app.services.model_services import get_embedding as config_get_embedding

logger = logging.getLogger("embedding_service")

EMBEDDING_MODEL = "bge-m3"
MODEL_VERSION = "bge-m3-v1"
EMBEDDING_DIM = 1024


def _build_vector_text(chunk: Chunk, fusion: PageFusion | None = None) -> str:
    parts = [chunk.content]
    if fusion and fusion.summary:
        parts.append(fusion.summary)
    return "\n".join(parts)


class EmbeddingService:

    _client: httpx.AsyncClient | None = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._client is None:
            cls._client = httpx.AsyncClient(timeout=60.0)
        return cls._client

    @classmethod
    async def get_embedding(cls, text: str) -> list[float]:
        return await config_get_embedding(text)

    @staticmethod
    async def vectorize_chunk(
        db: AsyncSession,
        chunk: Chunk,
    ) -> ChunkVector | None:
        fusion = None
        if chunk.source_fusion_id:
            result = await db.execute(
                select(PageFusion).where(PageFusion.id == chunk.source_fusion_id)
            )
            fusion = result.scalar_one_or_none()

        text = _build_vector_text(chunk, fusion)
        if not text.strip():
            return None

        embedding = await EmbeddingService.get_embedding(text)
        vector = ChunkVector(
            chunk_id=chunk.id,
            embedding=embedding,
            model_version=MODEL_VERSION,
            dim=EMBEDDING_DIM,
            normalized=True,
        )
        db.add(vector)
        await db.flush()
        await db.refresh(vector)
        return vector

    @staticmethod
    async def vectorize_chunks_batch(
        db: AsyncSession,
        chunk_ids: list[int] | None = None,
        catalog_id: int | None = None,
    ) -> int:
        if chunk_ids is not None and not chunk_ids:
            logger.info("Empty chunk_ids list, nothing to do")
            return 0

        stmt = select(Chunk).order_by(Chunk.id)
        if chunk_ids:
            stmt = stmt.where(Chunk.id.in_(chunk_ids))
        elif catalog_id is not None:
            stmt = stmt.where(Chunk.catalog_id == catalog_id)

        result = await db.execute(stmt)
        chunks = list(result.scalars().all())

        if not chunks:
            logger.info("No chunks to vectorize")
            return 0

        existing = await EmbeddingService._get_vectorized_chunk_ids(db)
        to_vectorize = [c for c in chunks if c.id not in existing]
        total = len(to_vectorize)
        success = 0

        for i, c in enumerate(to_vectorize):
            try:
                r = await EmbeddingService.vectorize_chunk(db, c)
                if r is not None:
                    success += 1
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.error("Vectorization error for chunk %d: %s", c.id, e)

            if (i + 1) % 10 == 0 or i == total - 1:
                logger.info("Vectorized %d/%d chunks", i + 1, total)

        logger.info(
            "Done: %d/%d chunks vectorized (skipped %d existing)",
            success, total, len(chunks) - total,
        )
        return success

    @staticmethod
    async def delete_vectors_for_chunks(
        db: AsyncSession, chunk_ids: list[int]
    ):
        if not chunk_ids:
            return
        await db.execute(
            delete(ChunkVector).where(ChunkVector.chunk_id.in_(chunk_ids))
        )
        await db.commit()

    @staticmethod
    async def _get_vectorized_chunk_ids(db: AsyncSession) -> set[int]:
        result = await db.execute(
            select(ChunkVector.chunk_id).distinct()
        )
        return {row[0] for row in result.all()}

    @staticmethod
    async def verify_model_dimension() -> int:
        embedding = await EmbeddingService.get_embedding("验证维度")
        dim = len(embedding)
        logger.info("bge-m3 actual dimension: %d", dim)
        return dim
