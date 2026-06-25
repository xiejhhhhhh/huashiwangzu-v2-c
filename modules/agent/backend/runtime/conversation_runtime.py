"""ConversationRuntime — orchestrates the full chat turn.

HTTP handler only does: parse request, authenticate, call
``ConversationRuntime.execute()``, return the ``StreamingResponse``.

Owns initialization, user-message persistence, context assembly,
tool discovery, and wiring of the sub-runtime objects.
"""

from __future__ import annotations

import logging

from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

from ..init_db import run_init, ensure_user_profile
from ..schemas import ChatRequest
from ..engine.engine import assemble_context
from ..engine.event_store import record_event
from ..services import conversation_service as conv_svc
from ..services import tool_discovery
from .runtime_policy import RuntimePolicy
from .tool_loop_runtime import ToolLoopRuntime
from .task_sink import RuntimeTaskSink

logger = logging.getLogger("v2.agent").getChild("runtime.conversation")


class ConversationRuntime:
    """Orchestrates a single conversation turn end-to-end.

    Usage from ``chat.py``::

        runtime = ConversationRuntime()
        return await runtime.execute(payload, db, user)
    """

    def __init__(self, policy: RuntimePolicy | None = None) -> None:
        self.policy = policy or RuntimePolicy.default()

    async def execute(
        self,
        payload: ChatRequest,
        db: AsyncSession,
        user: User,
    ) -> StreamingResponse:
        """Execute the full chat turn and return a StreamingResponse.

        Steps:
        1. ``run_init`` / ``ensure_user_profile``
        2. Persist user message
        3. ``assemble_context`` + record assembly diagnostic
        4. Build tool list
        5. Create ``ToolLoopRuntime`` + ``RuntimeTaskSink``
        6. Return ``StreamingResponse`` over the tool-loop generator
        """
        await run_init(db)
        await ensure_user_profile(db, user.id)

        # ── Persist user message ────────────────────────────────────
        await conv_svc.add_message(
            db, user.id, payload.conversation_id, "user", payload.content,
        )
        await record_event(
            db, payload.conversation_id, "user_msg",
            {"content": payload.content},
        )

        # ── Assemble context ────────────────────────────────────────
        profile_key = payload.profile_key or "deepseek-v4-flash"
        agent_code = "erp_chat"
        messages, engine_diag = await assemble_context(
            db, payload.conversation_id, payload.content,
            profile_key, user.id, agent_code=agent_code,
        )

        # ── Record assembly diagnostic ──────────────────────────────
        try:
            await record_event(
                db, payload.conversation_id, "assembly_diag",
                {
                    "total_estimated": engine_diag.get("total_estimated", 0),
                    "budget": engine_diag.get("budget"),
                    "system_tokens": engine_diag.get("system_tokens", 0),
                    "input_tokens": engine_diag.get("input_tokens", 0),
                    "recent_tokens": engine_diag.get("recent_tokens", 0),
                    "experience_injection": engine_diag.get("experience_injection", ""),
                    "experience_injected": engine_diag.get("experience_injected", []),
                    "dropped_recent_count": engine_diag.get("dropped_recent_count", 0),
                    "budget_exceeded": engine_diag.get("budget_exceeded", False),
                    "is_unlimited": engine_diag.get("is_unlimited", False),
                },
                llm_response_id=None,
            )
        except Exception as diag_exc:
            logger.warning(
                "Record assembly diag failed (non-fatal): %s", diag_exc,
            )

        # ── Build tools ─────────────────────────────────────────────
        tools = tool_discovery.build_tools(user.role)

        # ── Wire sub-runtimes ───────────────────────────────────────
        sink = RuntimeTaskSink(
            conversation_id=payload.conversation_id,
            owner_id=user.id,
            profile_key=profile_key,
        )
        loop = ToolLoopRuntime(
            conversation_id=payload.conversation_id,
            owner_id=user.id,
            profile_key=profile_key,
            policy=self.policy,
        )

        async def _event_stream():
            async for event in loop.run(messages, tools, sink):
                yield event

        return StreamingResponse(_event_stream(), media_type="text/event-stream")
