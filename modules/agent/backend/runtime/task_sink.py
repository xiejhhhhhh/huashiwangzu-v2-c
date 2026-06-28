"""RuntimeTaskSink — unified persistence and post-turn hook gateway.

Consolidates assistant message persistence, event flushing, timeline
storage, and hook triggering — all the scatter-shot DB work that used
to live at the bottom of ``event_stream()`` in ``chat.py``.

Also records Agent asset entries: when a tool result contains a
``file_id``, a ``FileAsset`` record is created so the file is
traceable back to the conversation, tool, and tool call that produced it.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.database import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession

from .._utils import references_from_tool_events
from ..engine.engine import get_hooks
from ..engine.event_store import record_event as _record_event
from ..engine.failure_diagnostics import record_failure as _record_failure
from ..runtime.content_gate import (
    extract_inline_references,
    extract_success_path,
    final_clean_content,
)
from ..services import conversation_service as conv_svc

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
        usage: dict | None = None,
    ) -> int | None:
        """Save the assistant message, meta, and return the message id."""
        if not full_content:
            return None

        clean_content = final_clean_content("".join(full_content))
        inline_references = extract_inline_references("".join(full_content))
        success_path = extract_success_path("".join(full_content))
        if success_path:
            try:
                from ..engine.experience_memory import save_experience
                await save_experience(
                    trigger_condition=clean_content[:300] or "assistant_success_path",
                    steps=success_path,
                    source_conversation_id=self.conversation_id,
                    caller=f"user:{self.owner_id}" if self.owner_id else "system:agent",
                )
            except Exception as exc:
                logger.warning("success path extraction save failed (non-fatal): %s", exc)
        if not clean_content:
            logger.warning(
                "persist_assistant skipped — content cleared to empty by final_clean_content "
                "(conv=%d)", self.conversation_id,
            )
            return None
        msg = await conv_svc.add_message(
            db, self.owner_id, self.conversation_id,
            "assistant", clean_content,
        )
        safe_events = json.loads(json.dumps(tool_events, default=str))
        safe_timeline = json.loads(json.dumps(timeline, default=str))
        footer_references = inline_references or references_from_tool_events(tool_events)
        await conv_svc.add_message_meta(
            db,
            owner_id=self.owner_id,
            conversation_id=self.conversation_id,
            message_id=msg.id,
            thinking="\n".join(thinking_parts) if thinking_parts else "",
            references=footer_references,
            tool_events=safe_events,
            timeline=safe_timeline,
            usage=usage,
        )
        logger.info(
            "[DIAG] persist_assistant DONE msg=%d timeline_len=%d full_len=%d usage=%s",
            msg.id, len(timeline), len(full_content),
            json.dumps(usage) if usage else "None",
        )
        return msg.id

    async def persist_pending_events(
        self,
        db: AsyncSession,
        pending_events: list[dict],
        persisted_count: int = 0,
    ) -> int:
        """Flush unpersisted events from *pending_events*.

        Returns the count of events that were successfully persisted
        (``persisted_count + new_count``), so failed events are retried
        on the next incremental persist rather than silently lost.
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
        return persisted_count + new_count

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

    async def record_assets(
        self,
        tool_results: list[dict],
        skip_file_ids: set[int] | None = None,
    ) -> list[int]:
        """Scan tool results for file_id outputs and create asset records.

        Each tool result dict should have keys:
            name: str         — tool name (e.g. "office-gen__docx")
            result: dict      — tool result, may contain "file_id"
            tool_call_id: str — unique tool call identifier

        Returns list of created asset IDs.
        """
        if not tool_results:
            return []
        asset_ids: list[int] = []
        try:
            from app.services.asset_service import create_asset

            async with AsyncSessionLocal() as _ad:
                for tr in tool_results:
                    result_data = tr.get("result", {})
                    if isinstance(result_data, dict):
                        inner = result_data.get("data", result_data)
                        file_id = inner.get("file_id") if isinstance(inner, dict) else None
                    else:
                        file_id = None
                    if not file_id:
                        continue
                    if skip_file_ids and file_id in skip_file_ids:
                        continue
                    try:
                        asset = await create_asset(
                            _ad,
                            file_id=file_id,
                            owner_id=self.owner_id,
                            asset_type="generated",
                            conversation_id=self.conversation_id,
                            tool_name=tr.get("name", ""),
                            tool_call_id=tr.get("tool_call_id") or "",
                        )
                        asset_ids.append(asset.id)
                        logger.info(
                            "Asset auto-created: id=%d file_id=%d tool=%s conv=%d",
                            asset.id, file_id, tr.get("name", ""),
                            self.conversation_id,
                        )
                    except Exception as _ae:
                        logger.warning(
                            "Asset create skipped for file_id=%d tool=%s (non-fatal): %s",
                            file_id, tr.get("name", ""), _ae,
                        )
        except Exception as exc:
            logger.warning(
                "record_assets failed (non-fatal): %s", exc,
            )
        return asset_ids

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
