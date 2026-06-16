import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.agent.tools")


@dataclass
class ToolResult:
    success: bool = True
    data: Any = None
    error: str | None = None


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)

    @abstractmethod
    async def execute(self, db: AsyncSession, user_id: int, **kwargs) -> ToolResult:
        ...

    def to_spec(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        logger.info("Tool registered: %s", tool.name)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [t.to_spec() for t in self._tools.values()]

    async def call_tool(self, db: AsyncSession, user_id: int, name: str, **kwargs) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(success=False, error=f"Tool '{name}' not found")
        try:
            return await tool.execute(db, user_id, **kwargs)
        except Exception as e:
            logger.exception("Tool call '%s' failed", name)
            return ToolResult(success=False, error=str(e))


tool_registry = ToolRegistry()
