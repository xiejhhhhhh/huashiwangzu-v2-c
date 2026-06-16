from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEvaluation
from app.services.agent.tools.registry import BaseTool, ToolResult


class ReadLatestEvaluationTool(BaseTool):
    name = "read_latest_evaluation"
    description = "Read the latest knowledge evaluation report"
    parameters = {
        "type": "object",
        "properties": {
            "include_details": {"type": "boolean", "description": "Include question-level details", "default": False},
        },
        "required": [],
    }

    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        include_details = bool(kwargs.get("include_details", False))
        result = await db.execute(
            select(KnowledgeEvaluation).order_by(desc(KnowledgeEvaluation.id)).limit(1)
        )
        record = result.scalar_one_or_none()
        if not record:
            return ToolResult(data={"latest": None})
        return ToolResult(data={"latest": _serialize(record, include_details=include_details)})


def _serialize(record: KnowledgeEvaluation, include_details: bool = False) -> dict:
    data = {
        "id": record.id,
        "datasetName": record.dataset_name,
        "datasetVersion": record.dataset_version,
        "status": record.status,
        "questionCount": record.question_count,
        "passedCount": record.passed_count,
        "averageScore": record.average_score,
        "recallRate": record.recall_rate,
        "hallucinationRate": record.hallucination_rate,
        "averageLatencyMs": record.average_latency_ms,
        "summary": record.summary or {},
        "error": record.error,
        "createdAt": record.created_at.isoformat() if record.created_at else None,
    }
    if include_details:
        data["details"] = (record.details or {}).get("items", [])
    return data
