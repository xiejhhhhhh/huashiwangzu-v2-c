import logging
from sqlalchemy import text, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge import Entity

logger = logging.getLogger(__name__)


async def dict_recall(
    db: AsyncSession,
    query: str,
    top_k: int = 20,
) -> list[dict]:
    tokens = query.strip().split()
    if not tokens:
        return []

    conditions = [Entity.standard_name.ilike(f"%{tok}%") for tok in tokens]
    stmt = (
        select(Entity)
        .where(or_(*conditions))
        .where(Entity.confirm_status.in_(["confirmed", "pending"]))
        .limit(top_k)
    )
    result = await db.execute(stmt)
    entities = result.scalars().all()

    if not entities:
        return []

    entity_names = [e.standard_name for e in entities]

    params = {}
    clause_parts = []
    for i, name in enumerate(entity_names):
        clause_parts.append(f"pf.fusion_text ILIKE :n{i}")
        params[f"n{i}"] = f"%{name}%"
    params["top_k"] = top_k

    where_clause = " OR ".join(clause_parts)

    sql = text(f"""
        SELECT DISTINCT ON (pf.id)
            pf.id AS source_id,
            pf.catalog_id,
            pf.page_num,
            pf.fusion_text,
            pf.summary,
            pf.attributes,
            pf.labels,
            0.8 AS score
        FROM knowledge_page_fusions pf
        WHERE ({where_clause})
        LIMIT :top_k
    """)

    result = await db.execute(sql, params)
    rows = result.all()

    return [
        {
            "recall_type": "dict",
            "source_id": r.source_id,
            "catalog_id": r.catalog_id,
            "page_num": r.page_num,
            "fusion_text": (r.fusion_text or "")[:500],
            "summary": r.summary,
            "attributes": r.attributes,
            "labels": r.labels,
            "score": round(float(r.score), 4),
        }
        for r in rows
    ]
