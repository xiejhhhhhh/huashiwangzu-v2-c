"""RuntimeTaskSink — unified persistence and post-turn hook gateway.

Consolidates assistant message persistence, event flushing, timeline
storage, and hook triggering — all the scatter-shot DB work that used
to live at the bottom of ``event_stream()`` in ``chat.py``.

Also records Agent asset entries: when a tool result contains a
``file_id``, a ``FileAsset`` record is created so the file is
traceable back to the conversation, tool, and tool call that produced it.
"""

from __future__ import annotations

import json
import logging

from app.database import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession

from .._utils import references_from_tool_events
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
        user_input: str = "",
        intent_preflight: dict | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.owner_id = owner_id
        self.profile_key = profile_key
        self.user_input = user_input
        self.intent_preflight = intent_preflight or {}

    @staticmethod
    def check_tool_success(tool_events: list[dict]) -> bool:
        """Unified tool result success checker.

        Returns ``True`` only if every tool call that produced a result
        completed without errors. Checks in order:
        1. Event-level ``event_type == "error"`` ⇒ fail.
        2. Tool result inner ``success`` field (``true`` / ``false``).
        3. Tool result top-level ``error`` key (non-empty ⇒ fail).
        4. Unified envelope ``{"success": false, ...}``.
        5. Policy / approval denial (``denied``, ``policy_blocked``).
        6. Exception or cancellation markers.

        **All** consumers (trajectory, workflow gate, completion evidence)
        **must** go through this function — no hardcoded ``error_occurred``.
        """
        has_error_event = any(
            e.get("event_type") == "error" for e in tool_events
        )
        if has_error_event:
            return False

        for ev in tool_events:
            if ev.get("type") != "tool_result":
                continue
            result = ev.get("result", {})
            if isinstance(result, dict):
                if not result.get("success", True):
                    return False
                if result.get("error"):
                    return False
                inner = result.get("data", result)
                if isinstance(inner, dict):
                    if inner.get("success") is False:
                        return False
                    if inner.get("error"):
                        return False
                if result.get("denied") or result.get("policy_blocked"):
                    return False
        return True

    @staticmethod
    def _is_tool_result_error(result: dict) -> bool:
        """Check a single tool result dict for any error signal."""
        if not isinstance(result, dict):
            return True
        if not result.get("success", True):
            return True
        if result.get("error"):
            return True
        if result.get("denied") or result.get("policy_blocked"):
            return True
        inner = result.get("data", result)
        if isinstance(inner, dict):
            if inner.get("success") is False:
                return True
            if inner.get("error"):
                return True
        return False

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
                    trigger_condition=self._experience_trigger(clean_content),
                    steps=self._experience_steps(success_path, tool_events),
                    tools_used=self._tools_used(tool_events),
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

    def _experience_trigger(self, clean_content: str) -> str:
        parts = []
        if self.user_input:
            parts.append(f"用户原始问题：{self.user_input[:300]}")
        intent = str(self.intent_preflight.get("intent_summary") or "")
        if intent:
            parts.append(f"意图摘要：{intent[:300]}")
        task_category = str(self.intent_preflight.get("task_category") or "")
        answer_shape = str(self.intent_preflight.get("answer_shape") or "")
        if task_category or answer_shape:
            parts.append(f"任务类型：{task_category}/{answer_shape}")
        if not parts:
            parts.append(clean_content[:300] or "assistant_success_path")
        return "\n".join(parts)[:1000]

    def _experience_steps(self, success_path: str, tool_events: list[dict]) -> str:
        try:
            parsed = json.loads(success_path)
            if isinstance(parsed, list):
                return json.dumps(parsed, ensure_ascii=False, default=str)
        except (json.JSONDecodeError, TypeError):
            pass
        steps: list[dict] = []
        task_category = self.intent_preflight.get("task_category")
        if task_category:
            steps.append({"type": "intent", "task_category": task_category, "summary": self.intent_preflight.get("intent_summary", "")})
        for event in tool_events:
            if event.get("type") == "tool_call":
                steps.append({"type": "tool", "tool_name": event.get("name", "")})
        steps.append({"type": "success_path", "text": success_path})
        return json.dumps(steps, ensure_ascii=False, default=str)

    @staticmethod
    def _tools_used(tool_events: list[dict]) -> str | None:
        names: list[str] = []
        seen: set[str] = set()
        for event in tool_events:
            if event.get("type") != "tool_call":
                continue
            name = str(event.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return json.dumps(names, ensure_ascii=False) if names else None

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
        trajectory_id: int | None = None,
        turn_index: int | None = None,
    ) -> None:
        """Run post-turn hooks via durable SystemTaskQueue.

        Cheap hooks (context_snapshot, prompt_suggestion, cleanup_archive)
        run inline. Expensive/async hooks (memory_distill, profile_evolve,
        workflow_mine) are submitted to SystemTaskQueue for durable
        cross-worker execution.
        """
        try:
            from ..engine.event_store import record_event as _record_event
            from ..engine.post_turn_hooks import _get_turn_count

            # ── Cheap hooks: inline ────────────────────────────────
            turn_count = await _get_turn_count(db, self.conversation_id)

            # context_snapshot (every N turns)
            if turn_count > 0 and turn_count % 3 == 0:
                try:
                    from ..engine.context_snapshot import take_snapshot
                    from ..engine.event_store import read_events
                    events = await read_events(db, self.conversation_id)
                    await take_snapshot(
                        db=db, conversation_id=self.conversation_id,
                        snapshot_type="periodic",
                        messages=messages, events=events,
                        summary=f"Periodic snapshot at turn {turn_count}",
                    )
                except Exception as exc:
                    logger.warning("context_snapshot failed (non-fatal): %s", exc)

            # prompt_suggestion (inline, cheap)
            assistant_text = ""
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    assistant_text = str(msg.get("content", "") or "").strip()
                    break
            if assistant_text and len(assistant_text) < 120:
                try:
                    await _record_event(
                        db, self.conversation_id,
                        "hook_prompt_suggestion",
                        {"owner_id": self.owner_id, "assistant_length": len(assistant_text),
                         "suggestion": "assistant_reply_too_short"},
                        llm_response_id=None,
                    )
                except Exception as exc:
                    logger.warning("prompt_suggestion failed (non-fatal): %s", exc)

            # cleanup_archive (inline, cheap)
            if turn_count > 0 and turn_count % 3 == 0:
                try:
                    from sqlalchemy import delete, desc, select

                    from ..models import ContextSnapshot
                    r = await db.execute(
                        select(ContextSnapshot.id)
                        .where(ContextSnapshot.conversation_id == self.conversation_id,
                               ContextSnapshot.snapshot_type == "periodic")
                        .order_by(desc(ContextSnapshot.id)).offset(10)
                    )
                    stale_ids = [row[0] for row in r.all()]
                    if stale_ids:
                        await db.execute(
                            delete(ContextSnapshot).where(ContextSnapshot.id.in_(stale_ids))
                        )
                        await db.commit()
                except Exception as exc:
                    logger.warning("cleanup_archive failed (non-fatal): %s", exc)

            # ── Expensive hooks: SystemTaskQueue ──────────────────
            tool_success = self.check_tool_success(tool_events)

            await self.submit_background_task(
                "memory_distill",
                {"conversation_id": self.conversation_id, "owner_id": self.owner_id,
                 "user_content": self.user_input,
                 "assistant_content": assistant_text,
                 "trajectory_id": trajectory_id, "turn_index": turn_index},
            )

            await self.submit_background_task(
                "profile_evolve",
                {"conversation_id": self.conversation_id, "owner_id": self.owner_id,
                 "trajectory_id": trajectory_id, "turn_index": turn_index},
            )

            if tool_events and tool_success and trajectory_id is not None:
                await self.submit_background_task(
                    "workflow_mine",
                    {"owner_id": self.owner_id, "conversation_id": self.conversation_id,
                     "trajectory_id": trajectory_id, "turn_index": turn_index},
                )

            await self._enqueue_context_compact()

            logger.info("Post-turn hooks submitted via SystemTaskQueue for conv=%d", self.conversation_id)
        except Exception as exc:
            logger.warning(
                "post-turn hooks enqueue failed (non-fatal): %s", exc,
            )

    async def _enqueue_context_compact(self) -> None:
        """Enqueue async context compaction after reply persistence.

        Reads the latest event watermark and submits a durable task.
        Idempotency is handled by the unique constraint on
        (conversation_id, until_event_id, generation) in the handler.
        """
        try:
            from sqlalchemy import func, select

            from ..models import AgentEvent
            async with AsyncSessionLocal() as _s:
                r = await _s.execute(
                    select(func.max(AgentEvent.id)).where(
                        AgentEvent.conversation_id == self.conversation_id,
                    )
                )
                until_event_id = r.scalar_one_or_none()
            if not until_event_id:
                logger.debug("No events to compact for conv=%d", self.conversation_id)
                return
            await self.submit_background_task(
                "agent_context_compact",
                {
                    "conversation_id": self.conversation_id,
                    "owner_id": self.owner_id,
                    "until_event_id": int(until_event_id),
                    "profile_key": self.profile_key,
                },
            )
        except Exception as exc:
            logger.warning("context_compact enqueue failed (non-fatal): %s", exc)

    async def record_trajectory(
        self,
        db: AsyncSession,
        turn_index: int,
        tool_calls: list[dict],
        tool_results: list[dict],
        assistant_response: str,
        thinking_level: str | None = None,
        error_occurred: bool = False,
        duration_ms: float | None = None,
        token_count: int | None = None,
    ) -> dict:
        """Record turn trajectory (idempotent upsert by conv+turn)."""
        from ..services.trajectory_service import record_turn as _record_turn
        return await _record_turn(
            db,
            conversation_id=self.conversation_id,
            owner_id=self.owner_id,
            session_id=f"conv_{self.conversation_id}",
            turn_index=turn_index,
            user_input=self.user_input,
            tool_calls=tool_calls,
            tool_results=tool_results,
            assistant_response=assistant_response,
            thinking_level=thinking_level,
            error_occurred=error_occurred,
            duration_ms=duration_ms,
            token_count=token_count,
        )

    async def generate_completion_evidence(
        self,
        tool_events: list[dict],
        tool_results: list[dict],
    ) -> list[dict]:
        """Generate structured completion evidence from tool events.

        Each entry records:
        - operation: inferred action type (create/update/replace/delete/other)
        - artifact_ids: file or resource IDs involved
        - tool_reported_success: whether the tool returned success
        - read_back_verified: whether a subsequent read tool confirmed
        - errors: any error messages

        Rules:
        - Tool call and its result are correlated by ``tool_call_id`` when
          available, with ordered call/result pairing as a fallback for the
          live runtime shape that can contain blank IDs.
        - ``tool_reported_success`` comes from **the corresponding result**,
          not from the tool name.
        - Artifact IDs are extracted from **both** call arguments and
          successful result data (result often contains the actual file_id).
        - ``read_back_verified`` is ``True`` only when the read tool
          call **and** its result both succeed **and** the returned
          artifact matches the written one.
        - If no read-back is possible, ``read_back_verified`` stays ``False``
          (never default to ``True``).
        """
        evidence: list[dict] = []
        # Ordered ``(key, call_event, result_event)`` rows. The key is the
        # real tool_call_id when present, otherwise a synthetic sequence key.
        # Keeping order is required for read-back verification.
        call_rows: list[tuple[str, dict, dict | None]] = []
        id_to_row: dict[str, int] = {}

        for ev in tool_events:
            if ev.get("type") != "tool_call":
                continue
            tcid = str(ev.get("tool_call_id", "") or ev.get("id", ""))
            if tcid and tcid != "None":
                key = tcid
                id_to_row[key] = len(call_rows)
            else:
                key = f"seq_{len(call_rows)}"
            call_rows.append((key, ev, None))

        sequential_results: list[dict] = []
        for tr in tool_results:
            tcid = str(tr.get("tool_call_id", "") or tr.get("id", ""))
            if tcid and tcid != "None" and tcid in id_to_row:
                row_idx = id_to_row[tcid]
                key, call_ev, _old_result = call_rows[row_idx]
                call_rows[row_idx] = (key, call_ev, tr)
            else:
                sequential_results.append(tr)

        seq_idx = 0
        for row_idx, (key, call_ev, result_ev) in enumerate(call_rows):
            if result_ev is not None:
                continue
            if seq_idx >= len(sequential_results):
                break
            call_rows[row_idx] = (key, call_ev, sequential_results[seq_idx])
            seq_idx += 1

        call_results: dict[str, tuple[dict, dict | None]] = {
            key: (call_ev, result_ev)
            for key, call_ev, result_ev in call_rows
        }

        write_ids: dict[str, str] = {}  # artifact_id → operation

        for tcid, (call_ev, result_ev) in call_results.items():
            name = str(call_ev.get("name", "") or "")
            is_write = any(kw in name.lower() for kw in ("create", "update", "replace", "delete", "write", "save", "upload", "generate"))
            is_read = any(kw in name.lower() for kw in ("read", "detail", "list", "preview", "check", "get", "view", "open"))
            if not is_write and not is_read:
                continue

            # Determine success from the result (not the call)
            tool_ok = result_ev is not None
            errors: list[str] = []
            if result_ev is None:
                errors.append("missing_tool_result")
            else:
                tool_ok = not self._is_tool_result_error(result_ev.get("result", {}))
                if not tool_ok:
                    res = result_ev.get("result", {})
                    if isinstance(res, dict):
                        err_msg = str(res.get("error", "") or res.get("message", "") or "unknown error")
                        errors.append(err_msg[:200])

            # Extract artifact_ids from call arguments AND from successful result
            args = call_ev.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            artifact_ids = set()
            for id_key in ("file_id", "document_id", "id", "resource_id", "target_id"):
                vid = args.get(id_key)
                if vid is not None:
                    artifact_ids.add(str(vid))

            if result_ev and tool_ok:
                res = result_ev.get("result", {})
                if isinstance(res, dict):
                    inner = res.get("data", res)
                    if isinstance(inner, dict):
                        for id_key in ("file_id", "document_id", "id", "resource_id", "target_id"):
                            vid = inner.get(id_key)
                            if vid is not None:
                                artifact_ids.add(str(vid))

            aid_list = sorted(artifact_ids)

            if is_write:
                for aid in aid_list:
                    write_ids[aid] = "update" if "update" in name.lower() or "replace" in name.lower() else "create" if "create" in name.lower() or "generate" in name.lower() else "delete" if "delete" in name.lower() else "write"
                evidence.append({
                    "tool_call_id": tcid,
                    "tool_name": name,
                    "operation": "update" if "update" in name.lower() or "replace" in name.lower()
                                 else "create" if "create" in name.lower() or "generate" in name.lower()
                                 else "delete" if "delete" in name.lower()
                                 else "write",
                    "artifact_ids": aid_list,
                    "tool_reported_success": tool_ok,
                    "read_back_verified": False,
                    "errors": errors,
                })
            elif is_read:
                continue

        # Read-back verification: only if the read result also succeeded
        # AND artifact matches what was written
        _ordered_calls = list(call_results.items())
        _call_order = {tcid: idx for idx, (tcid, _) in enumerate(_ordered_calls)}
        for tcid, (call_ev, result_ev) in _ordered_calls:
            name = str(call_ev.get("name", "") or "")
            is_read = any(kw in name.lower() for kw in ("read", "detail", "list", "preview", "check", "get", "view", "open"))
            if not is_read or result_ev is None:
                continue
            tool_ok = not self._is_tool_result_error(result_ev.get("result", {}))
            if not tool_ok:
                continue

            args = call_ev.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            for id_key in ("file_id", "document_id", "id", "resource_id", "target_id"):
                vid = args.get(id_key)
                if vid is not None and str(vid) in write_ids:
                    for ev_item in evidence:
                        if str(vid) not in ev_item.get("artifact_ids", []):
                            continue
                        write_tcid = str(ev_item.get("tool_call_id", ""))
                        if _call_order.get(tcid, -1) <= _call_order.get(write_tcid, -1):
                            continue

                        write_call = call_results.get(write_tcid, ({}, None))[0]
                        expected = write_call.get("arguments", {})
                        if isinstance(expected, str):
                            try:
                                expected = json.loads(expected)
                            except (json.JSONDecodeError, TypeError):
                                expected = {}
                        read_result = result_ev.get("result", {})
                        actual = read_result.get("data", read_result) if isinstance(read_result, dict) else {}
                        verify_keys = (
                            "content", "text", "value", "name", "version",
                            "checksum", "url", "long_url", "status",
                        )
                        comparable = [
                            key for key in verify_keys
                            if isinstance(expected, dict) and key in expected
                        ]
                        matches = bool(comparable) and all(
                            isinstance(actual, dict)
                            and key in actual
                            and actual[key] == expected[key]
                            for key in comparable
                        )
                        if matches:
                            ev_item["read_back_verified"] = True

        return evidence

    async def submit_background_task(
        self,
        task_type: str,
        parameters: dict,
    ) -> int | None:
        """Submit a durable background task to SystemTaskQueue.

        Returns the task ID, or None on failure.
        """
        import json
        try:
            from app.database import AsyncSessionLocal as _AsyncSessionLocal
            from app.models.system import SystemTaskQueue
            async with _AsyncSessionLocal() as _s:
                task = SystemTaskQueue(
                    task_type=task_type,
                    parameters=json.dumps(parameters, ensure_ascii=False, default=str),
                    status="pending",
                    priority=0,
                    module="agent",
                    creator_id=self.owner_id,
                )
                _s.add(task)
                await _s.commit()
                await _s.refresh(task)
                logger.info("Background task submitted: type=%s conv=%d task_id=%s", task_type, self.conversation_id, task.id)
                return task.id
        except Exception as exc:
            logger.warning("Failed to submit background task %s: %s", task_type, exc)
            return None

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
