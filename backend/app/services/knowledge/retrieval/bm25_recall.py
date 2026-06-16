import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def bm25_recall(
    db: AsyncSession,
    query: str,
    top_k: int = 20,
    catalog_id: int | None = None,
) -> list[dict]:
    return await _bm25_ilike(db, query, top_k, catalog_id)


async def _bm25_ilike(
    db: AsyncSession,
    query: str,
    top_k: int = 20,
    catalog_id: int | None = None,
) -> list[dict]:
    tokens = query.strip().split()
    if not tokens:
        return []

    params = {}
    clause_parts = []
    for i, tok in enumerate(tokens):
        clause_parts.append(f"(pf.fusion_text ILIKE :t{i} OR pf.summary ILIKE :t{i})")
        params[f"t{i}"] = f"%{tok}%"
    params["top_k"] = top_k

    conditions = " OR ".join(clause_parts)

    if catalog_id is not None:
        params["catalog_id"] = catalog_id
        sql = text(f"""
            SELECT
                pf.id AS source_id,
                pf.catalog_id,
                pf.page_num,
                pf.fusion_text,
                pf.summary,
                pf.attributes,
                pf.labels,
                pf.quality_score,
                0.1 AS score
            FROM knowledge_page_fusions pf
            WHERE ({conditions}) AND pf.catalog_id = :catalog_id
            LIMIT :top_k
        """)
    else:
        sql = text(f"""
            SELECT
                pf.id AS source_id,
                pf.catalog_id,
                pf.page_num,
                pf.fusion_text,
                pf.summary,
                pf.attributes,
                pf.labels,
                pf.quality_score,
                0.1 AS score
            FROM knowledge_page_fusions pf
            WHERE ({conditions})
            LIMIT :top_k
        """)

    result = await db.execute(sql, params)
    rows = result.all()

    return [
        {
            "recall_type": "bm25",
            "source_id": r.source_id,
            "catalog_id": r.catalog_id,
            "page_num": r.page_num,
            "fusion_text": (r.fusion_text or "")[:500],
            "summary": r.summary,
            "attributes": r.attributes,
            "labels": r.labels,
            "quality_score": r.quality_score,
            "score": round(float(r.score), 4),
        }
        for r in rows
    ]
