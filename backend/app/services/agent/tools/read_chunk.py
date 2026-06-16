from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.agent.tools.registry import BaseTool, ToolResult, tool_registry
from app.models.knowledge import Chunk, Catalog


class ReadChunkTool(BaseTool):
    name = "read_chunk"
    description = "Read a single chunk detail by chunk ID"
    parameters = {
        "type": "object",
        "properties": {
            "chunk_id": {"type": "integer", "description": "Chunk ID"},
        },
        "required": ["chunk_id"],
    }

    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        chunk_id = kwargs.get("chunk_id")
        if not chunk_id:
            return ToolResult(success=False, error="chunk_id is required")

        chunk = await db.get(Chunk, chunk_id)
        if not chunk:
            return ToolResult(success=False, error=f"Chunk {chunk_id} not found")

        catalog = await db.get(Catalog, chunk.catalog_id)
        file_name = catalog.file_name if catalog else ""

        return ToolResult(data={
            "chunk_id": chunk.id,
            "catalog_id": chunk.catalog_id,
            "file_name": file_name,
            "content": chunk.content,
            "page_num": chunk.page_num,
            "char_offset": chunk.char_offset,
            "tokens": chunk.tokens,
            "chunk_meta": chunk.chunk_meta if chunk.chunk_meta else {},
            "source_fusion_id": chunk.source_fusion_id,
        })
