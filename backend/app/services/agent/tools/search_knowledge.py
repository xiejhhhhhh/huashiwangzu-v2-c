import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.agent.tools.registry import BaseTool, ToolResult, tool_registry
from app.models.knowledge import PageFusion, Catalog
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class SearchKnowledgeTool(BaseTool):
    name = "search_knowledge"
    description = "Search the knowledge base. Provide a short focused query (2-5 Chinese characters is best)."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Short focused search query (best with 2-5 chars, e.g. '清颜' not the full question)"},
            "top_k": {"type": "integer", "description": "Max results", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        query = kwargs.get("query", "")
        top_k = min(kwargs.get("top_k", 5), 50)
        if not query:
            return ToolResult(success=False, error="query is required")

        try:
            from app.services.knowledge.retrieval.hybrid import hybrid_search
            async with AsyncSessionLocal() as fresh_db:
                result = await hybrid_search(fresh_db, query, top_k=top_k)
            items = []
            for item in result.items:
                items.append({
                    "fusion_id": item.source_id,
                    "catalog_id": item.catalog_id,
                    "page_num": item.page_num,
                    "summary": item.summary,
                    "fusion_text_preview": item.fusion_text_preview,
                    "score": item.scores.combined if item.scores else 0,
                    "source_file_url": f"/api/knowledge/catalogs/{item.catalog_id}",
                })
            cat_ids = {it["catalog_id"] for it in items}
            if cat_ids:
                cat_result = await db.execute(select(Catalog).where(Catalog.id.in_(cat_ids)))
                cat_map = {c.id: c.file_name for c in cat_result.scalars().all()}
                for it in items:
                    it["file_name"] = cat_map.get(it["catalog_id"])
            return ToolResult(data={"items": items, "total": len(items), "query": query})
        except Exception as e:
            logger.warning("Hybrid search failed: %s, using ILIKE fallback", e)
            sql = text("""
                SELECT pf.id AS fusion_id, pf.catalog_id, pf.page_num,
                       pf.summary, pf.fusion_text, pf.attributes, pf.labels, pf.quality_score,
                       ct.file_name
                FROM knowledge_page_fusions pf
                JOIN catalogs ct ON ct.id = pf.catalog_id
                WHERE pf.summary ILIKE :q OR pf.fusion_text ILIKE :q
                ORDER BY pf.quality_score DESC NULLS LAST
                LIMIT :top_k
            """)
            result = await db.execute(sql, {"q": f"%{query}%", "top_k": top_k})
            rows = result.all()
            items = [{
                "fusion_id": r[0], "catalog_id": r[1], "page_num": r[2],
                "summary": r[3],
                "fusion_text_preview": (r[4] or "")[:300],
                "attributes": r[5] if r[5] else {},
                "labels": r[6] if r[6] else {},
                "quality_score": float(r[7]) if r[7] else 0.0,
                "file_name": r[8],
                "source_file_url": f"/api/knowledge/catalogs/{r[1]}",
            } for r in rows]
            return ToolResult(data={"items": items, "total": len(items), "query": query})
