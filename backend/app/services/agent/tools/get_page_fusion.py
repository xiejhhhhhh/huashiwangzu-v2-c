from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.agent.tools.registry import BaseTool, ToolResult, tool_registry
from app.models.knowledge import PageFusion, Catalog


class GetPageFusionTool(BaseTool):
    name = "get_page_fusion"
    description = "Read full page fusion content by fusion ID with optional segment offset/limit"
    parameters = {
        "type": "object",
        "properties": {
            "fusion_id": {"type": "integer", "description": "Page fusion ID"},
            "offset": {"type": "integer", "description": "Char offset for segmented reading", "default": 0},
            "limit": {"type": "integer", "description": "Max chars to return", "default": 2000},
        },
        "required": ["fusion_id"],
    }

    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        fusion_id = kwargs.get("fusion_id")
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 2000)
        if not fusion_id:
            return ToolResult(success=False, error="fusion_id is required")

        pf = await db.get(PageFusion, fusion_id)
        if not pf:
            return ToolResult(success=False, error=f"PageFusion {fusion_id} not found")

        catalog = await db.get(Catalog, pf.catalog_id)
        file_name = catalog.file_name if catalog else ""

        full_text = pf.fusion_text or ""
        segmented = full_text[offset:offset + limit]

        return ToolResult(data={
            "fusion_id": pf.id,
            "catalog_id": pf.catalog_id,
            "file_name": file_name,
            "page_num": pf.page_num,
            "fusion_text": segmented,
            "total_chars": len(full_text),
            "offset": offset,
            "returned_chars": len(segmented),
            "summary": pf.summary,
            "attributes": pf.attributes if pf.attributes else {},
            "labels": pf.labels if pf.labels else {},
            "evidence": pf.evidence if pf.evidence else {},
            "quality_score": float(pf.quality_score) if pf.quality_score else 0.0,
            "source_file_url": f"/api/knowledge/catalogs/{pf.catalog_id}",
        })
