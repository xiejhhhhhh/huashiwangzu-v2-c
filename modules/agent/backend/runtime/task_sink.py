"""RuntimeTaskSink — unified persistence and post-turn hook gateway.

Consolidates assistant message persistence, event flushing, timeline
storage, and hook triggering — all the scatter-shot DB work that used
to live at the bottom of ``event_stream()`` in ``chat.py``.

Future consumers (review-fork, artifact, task-ledger) will attach here.
"""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from .._utils import references_from_tool_events
from ..engine.engine import get_hooks
from ..engine.event_store import record_event as _record_event
from ..engine.failure_diagnostics import record_failure as _record_failure
from ..services import conversation_service as conv_svc
from ..services.model_client import final_clean_content

logger = logging.getLogger("v2.agent").getChild("runtime.task_sink")


class RuntimeTaskSink:
    """One-stop persistence gateway for a single conversation turn.

    Usage::

        sink = RuntimeTaskSink(conversation_id, owner_id)
        await sink.persist_assistant(...)
        await sink.persist_pending_events(...)
        await sink.run_post_turn_hooks(...)
    """

    def __init__(
        self,
        conversation_id: int,
        owner_id: int,
        profile_key: str = "deepseek-v4-flash",
    ) -> None:
        self.conversation_id = conversation_id
        self.owner_id = owner_id
        self.profile_key = profile_key

    async def persist_assistant(
        self,
        db: AsyncSession,
        full_content: str,
        thinking_parts: list[str],
        tool_events: list[dict],
        timeline: list[dict],
    ) -> int | None:
        """Save the assistant message, meta, and return the message id."""
        if not full_content:
            return None

        clean_content = final_clean_content("".join(full_content))
        msg = await conv_svc.add_message(
            db, self.owner_id, self.conversation_id,
            "assistant", clean_content,
        )
        safe_events = json.loads(json.dumps(tool_events, default=str))
        await conv_svc.add_message_meta(
            db,
            owner_id=self.owner_id,
            conversation_id=self.conversation_id,
            message_id=msg.id,
            thinking="\n".join(thinking_parts) if thinking_parts else "",
            references=references_from_tool_events(tool_events),
            tool_events=safe_events,
            timeline=timeline,
        )
        logger.info(
            "[DIAG] persist_assistant DONE msg=%d timeline_len=%d full_len=%d",
            msg.id, len(timeline), len(full_content),
        )
        return msg.id

    async def persist_pending_events(
        self,
        db: AsyncSession,
        pending_events: list[dict],
        persisted_count: int = 0,
    ) -> int:
        """Flush unpersisted events from *pending_events*.

        Returns the new ``persisted_count`` (``len(pending_events)``).
        """
        new_count = 0
        for pe in pending_events[persisted_count:]:
            try:
                await _record_event(
                    db, self.conversation_id,
                    pe["event_type"], pe["payload"],
                    pe.get("llm_response_id"),
                )
                new_count += 1
            except Exception as exc:
                logger.warning(
                    "persist_pending_events record_event failed (non-fatal): %s", exc,
                )
        logger.info(
            "[DIAG] persist_pending_events done (new=%d total=%d)",
            new_count, len(pending_events),
        )
        return len(pending_events)

    async def run_post_turn_hooks(
        self,
        db: AsyncSession,
        messages: list[dict],
        tool_events: list[dict],
        timeline: list[dict],
    ) -> None:
        """Fire-and-forget post-turn hooks after persistence."""
        try:
            hooks = get_hooks()
            asyncio.create_task(hooks.run_hooks(
                db, self.conversation_id, self.owner_id,
                messages, tool_events, timeline,
            ))
            logger.info("[DIAG] post-turn hooks enqueued")
        except Exception as exc:
            logger.warning(
                "post-turn hooks enqueue failed (non-fatal): %s", exc,
            )

    async def record_event(
        self,
        db: AsyncSession,
        event_type: str,
        payload: dict,
        llm_response_id: str | None = None,
    ) -> None:
        """Record a single event via event_store."""
        try:
            await _record_event(
                db, self.conversation_id, event_type, payload,
                llm_response_id=llm_response_id,
            )
        except Exception as exc:
            logger.warning(
                "record_event(%s) failed (non-fatal): %s", event_type, exc,
            )

    async def record_failure(
        self,
        source: str,
        operation: str,
        error_type: str,
        error_message: str,
    ) -> None:
        """Record a failure diagnostic."""
        try:
            await _record_failure(
                source, operation, error_type, error_message,
                conversation_id=self.conversation_id,
                owner_id=self.owner_id,
            )
        except Exception as exc:
            logger.warning(
                "record_failure failed (non-fatal): %s", exc,
            )
