import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.agent.tools.registry import tool_registry
from app.services.agent.tools.register_all import register_all_tools
from app.services.agent.citation_service import citation_service

logger = logging.getLogger("v2.agent.tools")

router = APIRouter(prefix="/api/agent", tags=["agent-tools"])

register_all_tools()


@router.get("/tools")
async def list_tools(
    user: User = Depends(require_permission("viewer")),
):
    tools = tool_registry.list_tools()
    return ApiResponse(data={"tools": tools, "total": len(tools)})


@router.post("/tools/{tool_name}/call")
async def call_tool(
    tool_name: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    args = body.get("arguments", {})
    result = await tool_registry.call_tool(db, user.id, tool_name, **args)
    return ApiResponse(
        success=result.success,
        data={"tool": tool_name, "result": result.data} if result.success else None,
        error=result.error if not result.success else None,
    )


@router.post("/citations/validate")
async def validate_citations(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    content = body.get("content", "")
    timeout = body.get("timeout", 10.0)
    result = await citation_service.validate_and_format(db, content, timeout)
    sources_md = citation_service.format_sources_markdown(result["sources"])
    return ApiResponse(data={
        "content": result["content"],
        "sources": result["sources"],
        "sourcesMarkdown": sources_md,
        "warning": result.get("warning"),
    })
