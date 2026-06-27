"""ConversationRuntime — orchestrates the full chat turn.

HTTP handler only does: parse request, authenticate, call
``ConversationRuntime.execute()``, return the ``StreamingResponse``.

Owns initialization, user-message persistence, context assembly,
tool discovery, understanding loop, and wiring of the sub-runtime objects.
"""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

from ..init_db import run_init, ensure_user_profile
from ..schemas import ChatRequest
from ..engine.engine import assemble_context
from ..engine.event_store import record_event
from ..services import conversation_service as conv_svc
from ..services import tool_discovery
from .checkpointer import PostgresCheckpointSaver
from .runtime_policy import RuntimePolicy
from .tool_loop_runtime import ToolLoopRuntime
from .task_sink import RuntimeTaskSink
from .understanding_loop import UnderstandingLoopOrchestrator

logger = logging.getLogger("v2.agent").getChild("runtime.conversation")


class ConversationRuntime:
    """Orchestrates a single conversation turn end-to-end.

    Usage from ``router.py``::

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

        Normal flow:
        1. ``run_init`` / ``ensure_user_profile``
        2. Persist user message
        3. ``assemble_context`` + record assembly diagnostic
        4. Run understanding loop (if high-ambiguity)
        5. Build tool list
        6. Create ``ToolLoopRuntime`` + ``RuntimeTaskSink``
        7. Return ``StreamingResponse`` over the tool-loop generator

        Resume flow (when ``resume_checkpoint_id`` is set):
        1. Load the checkpoint from DB
        2. Restore messages, tool_events, timeline, pending_events
        3. Create sink + loop with restored state
        4. Return ``StreamingResponse`` continuing from the checkpoint step
        """
        await run_init(db)
        await ensure_user_profile(db, user.id)

        profile_key = payload.profile_key or "deepseek-v4-flash"

        # ── Resume path: restore from checkpoint ────────────────────
        channel_values: dict | None = None
        if payload.resume_checkpoint_id:
            saver = PostgresCheckpointSaver()
            cp = await saver.get_tuple(
                db, payload.conversation_id, payload.resume_checkpoint_id,
            )
            if not cp:
                raise HTTPException(
                    status_code=404,
                    detail=f"Checkpoint {payload.resume_checkpoint_id} not found",
                )
            messages = cp["channel_values"]["messages"]
            cp["channel_values"]["resume_from_step"] = cp["step"]
            channel_values = cp["channel_values"]
            tools = tool_discovery.build_tools(user.role)
            logger.info(
                "Resuming conv=%d from checkpoint=%s step=%d with %d messages",
                payload.conversation_id, payload.resume_checkpoint_id,
                cp["step"], len(messages),
            )
        else:
            # ── Normal flow: persist user message ───────────────────
            await conv_svc.add_message(
                db, user.id, payload.conversation_id, "user", payload.content,
            )
            await record_event(
                db, payload.conversation_id, "user_msg",
                {"content": payload.content},
            )

            # ── Assemble context ────────────────────────────────────
            agent_code = "erp_chat"
            messages, engine_diag = await assemble_context(
                db, payload.conversation_id, payload.content,
                profile_key, user.id, agent_code=agent_code,
            )

            # ── Record assembly diagnostic ──────────────────────────
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

            # ── Understanding phase ─────────────────────────────────
            understanding_packet = None
            if self.policy.enable_understanding_loop and len(payload.content) >= self.policy.understanding_min_chars:
                try:
                    uloop = UnderstandingLoopOrchestrator(
                        conversation_id=payload.conversation_id,
                        owner_id=user.id,
                        profile_key=profile_key,
                    )
                    if await uloop.should_trigger(payload.content):
                        understanding_packet = await uloop.run(payload.content)
                        await record_event(
                            db, payload.conversation_id, "understanding_diag",
                            {
                                "triggered": True,
                                "roles_executed": understanding_packet.get("roles_executed", []),
                                "rounds_used": understanding_packet.get("rounds_used", 0),
                                "intent": understanding_packet.get("intent", "")[:200],
                                "summary": understanding_packet.get("summary", ""),
                            },
                        )
                        if understanding_packet.get("intent") or understanding_packet.get("summary"):
                            understanding_injection = self._build_understanding_injection(understanding_packet)
                            if understanding_injection and messages:
                                for msg in messages:
                                    if msg["role"] == "system":
                                        msg["content"] += understanding_injection
                                        break
                except Exception as uloop_exc:
                    logger.warning("Understanding loop failed (non-fatal): %s", uloop_exc)
                    await record_event(
                        db, payload.conversation_id, "understanding_diag",
                        {"triggered": True, "error": str(uloop_exc)},
                    )

            # ── Build tools ─────────────────────────────────────────
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
            async for event in loop.run(messages, tools, sink, channel_values=channel_values):
                yield event

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    def _build_understanding_injection(self, packet: dict) -> str:
        """Build a system-prompt injection from the understanding packet."""
        parts = []
        intent = packet.get("intent", "")
        if intent:
            parts.append(f"【意图理解】系统已识别用户核心意图：{intent}")
        concerns = packet.get("concerns", [])
        if concerns:
            top = concerns[:3]
            parts.append("【关注点】" + "; ".join(
                c.get("concern", "") for c in top if c.get("concern")
            ))
        plan = packet.get("plan_critique", "")
        if plan:
            try:
                plan_data = json.loads(plan)
                if isinstance(plan_data, dict):
                    feasibility = plan_data.get("feasibility", "")
                    approach = plan_data.get("suggested_approach", "")
                    if feasibility:
                        parts.append(f"【可行性评估】{feasibility}")
                    if approach:
                        parts.append(f"【建议方案】{approach}")
            except (json.JSONDecodeError, TypeError):
                logger.debug("Failed to parse plan_data from planning packet")
        retrieval = packet.get("retrieval_evidence", [])
        if retrieval:
            queries = [r.get("query", "") for r in retrieval if r.get("query")]
            if queries:
                parts.append(f"【可能需要检索】{' | '.join(queries[:3])}")
        if not parts:
            return ""
        return "\n\n---\n\n" + "\n".join(parts)
