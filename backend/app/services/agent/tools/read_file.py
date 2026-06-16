from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.agent.tools.registry import BaseTool, ToolResult, tool_registry
from app.models.knowledge import Catalog, DocProfile, Label


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read catalog/file profile with metadata, doc profile, and labels"
    parameters = {
        "type": "object",
        "properties": {
            "catalog_id": {"type": "integer", "description": "Catalog (file) ID"},
        },
        "required": ["catalog_id"],
    }

    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        catalog_id = kwargs.get("catalog_id")
        if not catalog_id:
            return ToolResult(success=False, error="catalog_id is required")

        catalog = await db.get(Catalog, catalog_id)
        if not catalog:
            return ToolResult(success=False, error=f"Catalog {catalog_id} not found")

        doc_profile = await db.execute(
            select(DocProfile).where(DocProfile.catalog_id == catalog_id)
        )
        profile = doc_profile.scalar_one_or_none()

        label_result = await db.execute(
            select(Label).where(Label.target_type == "file", Label.target_id == catalog_id)
        )
        labels = [{"label": l.label, "category": l.label_category} for l in label_result.scalars().all()]

        return ToolResult(data={
            "catalog_id": catalog.id,
            "file_name": catalog.file_name,
            "file_path": catalog.file_path,
            "file_size": catalog.file_size,
            "file_hash": catalog.file_hash,
            "mime_type": catalog.mime_type,
            "channel_type": catalog.channel_type,
            "status": catalog.status,
            "doc_profile": {
                "topic": profile.topic if profile else None,
                "doc_type": profile.doc_type if profile else None,
                "summary": profile.summary if profile else None,
                "key_entities": profile.key_entities if profile and profile.key_entities else {},
            } if profile else None,
            "labels": labels,
        })
