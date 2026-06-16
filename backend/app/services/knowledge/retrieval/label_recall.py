import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def label_recall(
    db: AsyncSession,
    query: str,
    top_k: int = 20,
) -> list[dict]:
    tokens = query.strip().split()
    if not tokens:
        return []

    params = {}
    clause_parts = []
    for i, tok in enumerate(tokens):
        clause_parts.append(f"l.label ILIKE :t{i}")
        params[f"t{i}"] = f"%{tok}%"
    params["top_k"] = top_k

    conditions = " OR ".join(clause_parts)

    sql = text(f"""
        SELECT
            pf.id AS source_id,
            pf.catalog_id,
            pf.page_num,
            pf.fusion_text,
            pf.summary,
            pf.attributes,
            l.label AS matched_label,
            l.label_category,
            l.target_type,
            l.target_id,
            1.0 AS score
        FROM knowledge_labels l
        JOIN knowledge_page_fusions pf ON
            l.target_type = 'file' AND l.target_id = pf.catalog_id
        WHERE ({conditions})
        LIMIT :top_k
    """)

    result = await db.execute(sql, params)
    rows = result.all()

    return [
        {
            "recall_type": "label",
            "source_id": r.source_id,
            "catalog_id": r.catalog_id,
            "page_num": r.page_num,
            "fusion_text": (r.fusion_text or "")[:500],
            "summary": r.summary,
            "attributes": r.attributes,
            "matched_label": r.matched_label,
            "label_category": r.label_category,
            "score": round(float(r.score), 4),
        }
        for r in rows
    ]
