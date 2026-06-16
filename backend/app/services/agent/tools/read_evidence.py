from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Catalog, Evidence, PageFusion
from app.services.agent.tools.registry import BaseTool, ToolResult


class ReadEvidenceTool(BaseTool):
    name = "read_evidence"
    description = "Read evidence details by evidence ID"
    parameters = {
        "type": "object",
        "properties": {
            "evidence_id": {"type": "integer", "description": "Evidence ID"},
        },
        "required": ["evidence_id"],
    }

    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        evidence_id = kwargs.get("evidence_id")
        if not evidence_id:
            return ToolResult(success=False, error="evidence_id is required")

        evidence = await db.get(Evidence, evidence_id)
        if not evidence:
            return ToolResult(success=False, error=f"Evidence {evidence_id} not found")

        catalog = await db.get(Catalog, evidence.catalog_id)
        fusion = None
        if evidence.source_type == "fusion":
            fusion = await db.get(PageFusion, evidence.source_id)

        return ToolResult(data={
            "evidence_id": evidence.id,
            "source_type": evidence.source_type,
            "source_id": evidence.source_id,
            "catalog_id": evidence.catalog_id,
            "file_name": catalog.file_name if catalog else "",
            "page_num": evidence.page_num,
            "confidence": evidence.confidence,
            "cross_verified": evidence.cross_verified,
            "bound_conclusions": evidence.bound_conclusions or {},
            "fusion_preview": (fusion.fusion_text or "")[:1000] if fusion else "",
        })
