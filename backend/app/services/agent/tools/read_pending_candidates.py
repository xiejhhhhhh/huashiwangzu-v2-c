from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import DisambigCandidate, ExtractCandidate
from app.services.agent.tools.registry import BaseTool, ToolResult


class ReadPendingCandidatesTool(BaseTool):
    name = "read_pending_candidates"
    description = "Read pending knowledge governance candidate counts"
    parameters = {"type": "object", "properties": {}, "required": []}

    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        extract_count = await db.scalar(
            select(func.count(ExtractCandidate.id)).where(ExtractCandidate.verdict_status == 0)
        )
        disambig_count = await db.scalar(
            select(func.count(DisambigCandidate.id)).where(DisambigCandidate.review_status == "pending")
        )
        return ToolResult(data={
            "pending_extract_candidates": extract_count or 0,
            "pending_disambig_candidates": disambig_count or 0,
            "total_pending": (extract_count or 0) + (disambig_count or 0),
        })
