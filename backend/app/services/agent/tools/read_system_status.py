from sqlalchemy.ext.asyncio import AsyncSession
from app.services.agent.tools.registry import BaseTool, ToolResult, tool_registry
from app.services import system_status_service


class ReadSystemStatusTool(BaseTool):
    name = "read_system_status"
    description = "Read overall system status including backend, database, worker, model service, CPU and memory"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        status = await system_status_service.get_system_status(db)
        return ToolResult(data=status)
