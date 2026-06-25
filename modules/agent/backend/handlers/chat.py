"""Chat endpoint handler for agent module — thin HTTP entry point.

All runtime logic has been extracted into ``modules/agent/backend/runtime/``.

``handle_chat`` now only: validate inputs, call ``ConversationRuntime``,
return ``StreamingResponse``.
"""

from __future__ import annotations

import logging

from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

from ..runtime import ConversationRuntime
from ..runtime.runtime_policy import RuntimePolicy
from ..schemas import ChatRequest

logger = logging.getLogger("v2.agent").getChild("handlers.chat")


async def handle_chat(payload: ChatRequest, db: AsyncSession, user: User) -> StreamingResponse:
    """Handle POST /api/agent/chat — thin entry point."""
    policy = RuntimePolicy.default()
    if payload.enable_checkpointer:
        policy.enable_checkpointer = True
    runtime = ConversationRuntime(policy=policy)
    return await runtime.execute(payload, db, user)
