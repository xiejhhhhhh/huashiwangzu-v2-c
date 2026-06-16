import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.knowledge_service import get_embedding

logger = logging.getLogger(__name__)


async def vector_recall(
    db: AsyncSession,
    query: str,
    top_k: int = 20,
    catalog_id: int | None = None,
) -> list[dict]:
    embedding = await get_embedding(query)
    if not embedding:
        logger.warning("vector_recall: embedding failed for query=%s", query)
        return []

    emb_str = "[" + ",".join(str(v) for v in embedding) + "]"

    where_clause = "WHERE cv.embedding IS NOT NULL"
    params = {"top_k": top_k}

    if catalog_id is not None:
        where_clause += " AND c.catalog_id = :catalog_id"
        params["catalog_id"] = catalog_id

    sql = text(f"""
        SELECT
            cv.chunk_id AS source_id,
            c.catalog_id,
            c.page_num,
            c.content,
            c.metadata AS chunk_meta,
            c.source_fusion_id,
            1 - (cv.embedding <=> CAST(:emb AS vector)) AS score
        FROM knowledge_chunk_vectors cv
        JOIN chunks c ON c.id = cv.chunk_id
        {where_clause}
        ORDER BY cv.embedding <=> CAST(:emb AS vector)
        LIMIT :top_k
    """)

    result = await db.execute(sql, {"emb": emb_str, **params})
    rows = result.all()

    return [
        {
            "recall_type": "vector",
            "source_id": r.source_fusion_id or r.source_id,
            "chunk_id": r.source_id,
            "catalog_id": r.catalog_id,
            "page_num": r.page_num,
            "fusion_text": r.content[:500] if r.content else "",
            "chunk_meta": r.chunk_meta,
            "score": round(float(r.score), 4) if r.score else 0.0,
        }
        for r in rows
    ]
