import logging
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.agent.session_service import session_service
from app.services.agent.chat_service import chat_service
from app.services.agent.gateway.router import gateway_router
from app.core.defaults import DEFAULT_AGENT_MODEL
from app.core.exceptions import NotFound, ValidationError

logger = logging.getLogger("v2.agent.session")
router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/sessions")
async def list_sessions(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    data = await session_service.list_sessions(db, user.id, page, pageSize)
    return ApiResponse(data=data)


@router.post("/sessions")
async def create_session(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    s = await session_service.create_session(
        db, user.id,
        title=body.get("title", "New Chat"),
        model=body.get("model", DEFAULT_AGENT_MODEL),
        system_prompt=body.get("systemPrompt"),
    )
    return ApiResponse(data={
        "id": s.id, "title": s.title, "model": s.model,
        "createdAt": s.created_at.isoformat() if s.created_at else "",
    })


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    s = await session_service.get_session(db, user.id, session_id)
    if not s:
        raise NotFound("Session not found")
    return ApiResponse(data={
        "id": s.id, "title": s.title, "model": s.model,
        "systemPrompt": s.system_prompt, "messageCount": s.message_count,
        "createdAt": s.created_at.isoformat() if s.created_at else "",
        "updatedAt": s.updated_at.isoformat() if s.updated_at else "",
    })


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    ok = await session_service.delete_session(db, user.id, session_id)
    if not ok:
        raise NotFound("Session not found")
    return ApiResponse(data={"message": "Session deleted"})


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: int,
    page: int = Query(1, ge=1),
    pageSize: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    s = await session_service.get_session(db, user.id, session_id)
    if not s:
        raise NotFound("Session not found")
    data = await chat_service.get_session_messages(db, session_id, page, pageSize)
    return ApiResponse(data=data)


@router.post("/sessions/{session_id}/message")
async def send_message(
    session_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    content = body.get("content", "")
    if not content:
        raise ValidationError("Content is required")
    profile_key = body.get("model", DEFAULT_AGENT_MODEL)
    result = await chat_service.send_message(db, user.id, session_id, content, profile_key)
    if not result["success"]:
        raise NotFound(result["error"])
    return ApiResponse(data=result["data"])


@router.post("/sessions/{session_id}/stream")
async def stream_message(
    session_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    content = body.get("content", "")
    if not content:
        raise ValidationError("Content is required")
    profile_key = body.get("model", DEFAULT_AGENT_MODEL)

    return StreamingResponse(
        chat_service.stream_message(db, user.id, session_id, content, profile_key),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/cancel")
async def cancel_stream(
    body: dict,
    user: User = Depends(require_permission("viewer")),
):
    session_id = body.get("sessionId", 0)
    chat_service.cancel_stream(session_id)
    return ApiResponse(data={"message": "Cancelled"})


@router.get("/providers")
async def list_providers(
    user: User = Depends(require_permission("viewer")),
):
    profiles = gateway_router.list_profiles()
    health = await gateway_router.check_all_health()
    return ApiResponse(data={"profiles": profiles, "health": health})


@router.get("/status")
async def agent_status(
    user: User = Depends(require_permission("viewer")),
):
    health = await gateway_router.check_all_health()
    return ApiResponse(data={
        "providers": health,
        "defaultModel": DEFAULT_AGENT_MODEL,
        "online": any(health.values()),
    })
