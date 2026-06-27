"""ToolLoopRuntime — the core tool-call loop as an async generator.

Extracted from ``event_stream()`` in ``chat.py``.  Yields SSE event
bytes and, on inline-tool-call re-entry, a dict signal.

Owns the round-iteration, stuck detection, diminishing-returns check,
tool classification (fast/slow), orchestration, and incremental event
persistence.  Uses ``StreamEmitter`` for the non-tool streaming turn and
``RuntimeTaskSink`` for all DB writes.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.database import AsyncSessionLocal

from .._utils import j as _j
from .._utils import tool_calls_for_history
from ..engine.budget_allocator import estimate_tokens
from ..engine.engine import (
    chat_with_degradation_chain,
    get_budget_tracker,
    get_orchestrator,
)
from ..engine.stuck_detector import detect_stuck
from ..engine.stuck_detector import reset as reset_stuck
from ..services import tool_discovery
from ..services.action_policy import check_action_allowed
from ..services.model_client import final_clean_content, parse_inline_tool_calls, recover_tool_calls
from .checkpointer import PostgresCheckpointSaver
from .runtime_policy import RuntimePolicy
from .stream_emitter import StreamEmitter
from .task_sink import RuntimeTaskSink

logger = logging.getLogger("v2.agent").getChild("runtime.tool_loop")


def detect_tool_round_stuck(tool_calls: list[dict], session_key: str) -> dict:
    if not tool_calls:
        return {"stuck": False}
    first_call = tool_calls[0]
    fn = first_call.get("function", first_call)
    return detect_stuck(
        tool_name=fn.get("name", ""),
        tool_args=fn.get("arguments", {}),
        error_text=None,
        is_empty_response=False,
        session_key=session_key,
    )


class ToolLoopRuntime:
    """Asynchronous tool-call loop with stop-policy enforcement.

    This is the "engine" of the conversation turn.  Iterate the
    ``run()`` async generator to receive SSE bytes (and possibly a
    single dict signal for re-entry).

    Typical usage by ``ConversationRuntime``::

        loop = ToolLoopRuntime(conversation_id, owner_id, profile_key, policy)
        async for event in loop.run(messages, tools, sink):
            yield event
    """

    def __init__(
        self,
        conversation_id: int,
        owner_id: int,
        profile_key: str = "deepseek-v4-flash",
        policy: RuntimePolicy | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.owner_id = owner_id
        self.profile_key = profile_key
        self.policy = policy or RuntimePolicy.default()

    async def run(
        self,
        messages: list[dict],
        tools: list[dict],
        sink: RuntimeTaskSink,
        channel_values: dict | None = None,
    ):
        """Async generator that yields SSE event bytes and possibly
        a dict ``{"type": "_inline_tool_calls", ...}``.

        If *channel_values* is provided (from a checkpoint resume), the
        internal state (tool_events, timeline, pending_events, event_round,
        persisted_event_count) is restored from it and the loop skips
        already-completed rounds (step+1 onward).

        Yields:
            - ``bytes``: SSE ``data: ...`` frames for ``StreamingResponse``
            - ``dict``: a control signal (currently only
              ``_inline_tool_calls``) — caller must re-enter the loop.
        """
        full: list[str] = []
        thinking_parts: list[str] = []
        tool_events: list[dict] = channel_values.get("tool_events", []) if channel_values else []
        timeline: list[dict] = channel_values.get("timeline", []) if channel_values else []
        pending_events: list[dict] = channel_values.get("pending_events", []) if channel_values else []
        event_round = channel_values.get("event_round", 0) if channel_values else 0
        persisted_event_count = channel_values.get("persisted_event_count", 0) if channel_values else 0
        _disconnected = False
        _last_checkpoint_id: str | None = None

        # If resuming from a checkpoint, skip already-completed rounds
        _resume_from_step = channel_values.get("resume_from_step", 0) if channel_values else 0

        try:
            # ── Reset sticky session state ─────────────────────────
            _session_key = f"conv_{self.conversation_id}"
            _budget_session_key = f"budget_conv_{self.conversation_id}"
            reset_stuck(_session_key)
            budget_tracker = get_budget_tracker()
            budget_tracker.reset(_budget_session_key)

            _tool_round_tokens_before = 0
            emitter = StreamEmitter()

            for _round in range(_resume_from_step, self.policy.max_tool_rounds):
                # Y1: reset full each round to avoid cross-round accumulation
                full = []
                logger.info(
                    "[DIAG] ToolLoopRuntime round %d/%d",
                    _round + 1, self.policy.max_tool_rounds,
                )

                # ── Non-streaming model call for tool decisions ─────
                result = await chat_with_degradation_chain(
                    messages,
                    self.profile_key,
                    tools,
                    conversation_id=self.conversation_id,
                )
                logger.info(
                    "[DIAG] ToolLoopRuntime chat returned tool_calls=%s error=%s",
                    bool(result.get("tool_calls")), bool(result.get("error")),
                )

                if result.get("error"):
                    error_msg = str(result["error"])
                    yield self._sse("error", error_msg)
                    break

                if result.get("thinking"):
                    thinking = str(result["thinking"])
                    thinking_parts.append(thinking)
                    timeline.append({"type": "thinking", "content": thinking})
                    yield self._sse("thinking", thinking)

                # ── Parse tool_calls with inline/tool recovery ──────
                tool_calls = result.get("tool_calls") or []
                if not tool_calls and result.get("finish_reason") == "tool_calls" and tools:
                    result = await recover_tool_calls(
                        messages, self.profile_key, tools,
                    )
                    tool_calls = result.get("tool_calls") or []

                if not tool_calls:
                    try:
                        clean_content, inline_calls = parse_inline_tool_calls(
                            result.get("content", ""),
                        )
                    except Exception as exc:
                        logger.warning(
                            "parse_inline_tool_calls failed (non-fatal): %s", exc,
                        )
                        clean_content, inline_calls = result.get("content", ""), []
                    if inline_calls:
                        result["content"] = clean_content
                        tool_calls = inline_calls

                # ── No tool calls → stream final content ────────────
                if not tool_calls:
                    inline_from_stream = None
                    async for chunk in emitter.yield_final_stream(
                        messages,
                        profile_key=self.profile_key,
                        tools=tools,
                        conversation_id=self.conversation_id,
                        owner_id=self.owner_id,
                        full_buffer=full,
                        thinking_buffer=thinking_parts,
                        timeline=timeline,
                    ):
                        if isinstance(chunk, dict) and chunk.get("type") == "_inline_tool_calls":
                            inline_from_stream = chunk.get("tool_calls", [])
                        else:
                            yield chunk
                    if inline_from_stream:
                        tool_calls = inline_from_stream
                        logger.info(
                            "[DIAG] ToolLoopRuntime re-entering with %d inline calls",
                            len(tool_calls),
                        )
                    else:
                        break

                # ── Record assistant turn in messages ───────────────
                content_source = "".join(full) if full else (result.get("content") or "")
                # DeepSeek requires content=null when tool_calls is present
                has_tc = bool(tool_calls)
                messages.append({
                    "role": "assistant",
                    "content": None if has_tc else content_source,
                    "tool_calls": tool_calls_for_history(tool_calls) if has_tc else None,
                })
                _event_round_id = f"round_{event_round}"
                event_round += 1
                pending_events.append({
                    "event_type": "assistant_msg",
                    "payload": {"content": content_source},
                    "llm_response_id": _event_round_id,
                })
                for tc in tool_calls:
                    fn = tc.get("function", tc)
                    raw_args = fn.get("arguments", {})
                    args_str = (
                        json.dumps(raw_args, ensure_ascii=False)
                        if isinstance(raw_args, dict)
                        else str(raw_args)
                    )
                    pending_events.append({
                        "event_type": "tool_call",
                        "payload": {
                            "id": tc.get("id") or fn.get("id") or "",
                            "name": fn.get("name", ""),
                            "arguments": args_str,
                        },
                        "llm_response_id": _event_round_id,
                    })

                # ── Phase 1: parse + classify tools ─────────────────
                parsed_tools: list[dict] = []
                for tc in tool_calls:
                    fn = tc.get("function", tc)
                    name = fn.get("name", "")
                    tool_call_id = tc.get("id") or fn.get("id") or ""
                    try:
                        args = fn.get("arguments") or {}
                        if isinstance(args, str):
                            args = json.loads(args)
                    except Exception:
                        args = {}
                    resolved_slow = None
                    if name == "skill_use":
                        inner_name = args.get("name", "")
                        if inner_name in self.policy.slow_skill_names:
                            resolved_slow = inner_name
                    elif name in self.policy.slow_skill_names:
                        resolved_slow = name
                    parsed_tools.append({
                        "name": name,
                        "tool_call_id": tool_call_id,
                        "args": args,
                        "slow_name": resolved_slow,
                    })
                    call_event = {"type": "tool_call", "name": name, "arguments": args}
                    tool_events.append(call_event)
                    timeline.append(call_event)
                    yield self._j_sse(call_event)

                # ── Phase 2: slow tools → background queue ──────────
                from ..handlers.tasks import _submit_slow_tool_task
                has_slow = False
                for tool in parsed_tools:
                    if not tool["slow_name"]:
                        continue
                    has_slow = True
                    task_id = await _submit_slow_tool_task(
                        conversation_id=self.conversation_id,
                        user_id=self.owner_id,
                        tool_name=tool["slow_name"],
                        skill_args=tool["args"],
                        caller=f"user:{self.owner_id}",
                        caller_role="viewer",  # pragmatic default
                    )
                    tool_result = {
                        "background": True,
                        "task_id": task_id,
                        "message": (
                            f"后台任务 [{tool['slow_name']}] 已提交，"
                            f"完成后将通过站内信通知你。"
                        ),
                    }
                    result_event = {
                        "type": "tool_result",
                        "name": tool["name"],
                        "result": tool_result,
                    }
                    tool_events.append(result_event)
                    timeline.append(result_event)
                    yield self._j_sse(result_event)
                    tool_message = {
                        "role": "tool",
                        "name": tool["name"],
                        "content": _j(tool_result),
                    }
                    if tool["tool_call_id"]:
                        tool_message["tool_call_id"] = tool["tool_call_id"]
                    messages.append(tool_message)
                    pending_events.append({
                        "event_type": "tool_result",
                        "payload": {
                            "tool_call_id": tool["tool_call_id"],
                            "name": tool["name"],
                            "result": tool_result,
                        },
                        "llm_response_id": None,
                    })

                if has_slow:
                    from ..models import AgentConversation
                    try:
                        async with AsyncSessionLocal() as _db:
                            _conv = await _db.get(
                                AgentConversation, self.conversation_id,
                            )
                            if _conv:
                                _conv.processing = True
                                await _db.commit()
                    except Exception as _pe:
                        logger.warning(
                            "Failed to mark processing flag: %s", _pe,
                        )

                # ── Phase 3: fast tools → ToolOrchestrator ──────────
                fast_tools = [t for t in parsed_tools if not t["slow_name"]]
                if fast_tools:
                    orchestrator = get_orchestrator()
                    AGENT_CODE = "erp_chat"

                    async def _tool_execute_fn(tool: dict) -> dict:
                        async with AsyncSessionLocal() as _pol_db:
                            pol = await check_action_allowed(
                                _pol_db, tool["name"], AGENT_CODE,
                                self.owner_id, self.conversation_id,
                            )
                        if not pol.get("allowed"):
                            return {
                                "policy_action": pol["action"],
                                "reason": pol.get("reason", ""),
                                "approval_id": pol.get("approval_id"),
                                "tool_name": pol.get("tool_name", tool["name"]),
                            }
                        if tool["name"] == "skill_list":
                            return await tool_discovery.handle_skill_list(
                                tool["args"], "admin",
                            )
                        elif tool["name"] == "skill_describe":
                            return await tool_discovery.handle_skill_describe(
                                tool["args"], "admin",
                            )
                        elif tool["name"] == "skill_use":
                            return await tool_discovery.handle_skill_use(
                                tool["args"],
                                caller=f"user:{self.owner_id}",
                                caller_role="admin",
                            )
                        else:
                            from app.services.module_registry import call_capability
                            module_key, action = tool_discovery.parse_tool_name(
                                tool["name"],
                            )
                            return await call_capability(
                                module_key, action, tool["args"],
                                caller=f"user:{self.owner_id}",
                                caller_role="admin",
                            )

                    orchestrator_tools = [
                        {
                            "name": t["name"],
                            "tool_call_id": t["tool_call_id"],
                            "args": t["args"],
                        }
                        for t in fast_tools
                    ]
                    orchestrated_results = await orchestrator.execute_batch(
                        orchestrator_tools, _tool_execute_fn,
                    )
                    for outcome in orchestrated_results:
                        result_data = (
                            outcome["result"]
                            if "result" in outcome
                            else {"error": outcome.get("error", "unknown")}
                        )
                        if isinstance(result_data, dict) and result_data.get("policy_action") == "confirm":
                            result_data["approval_required"] = True
                        result_event = {
                            "type": "tool_result",
                            "name": outcome["name"],
                            "result": result_data,
                        }
                        tool_events.append(result_event)
                        timeline.append(result_event)
                        yield self._j_sse(result_event)
                        tool_message = {
                            "role": "tool",
                            "name": outcome["name"],
                            "content": _j(result_data),
                        }
                        if outcome.get("tool_call_id"):
                            tool_message["tool_call_id"] = outcome["tool_call_id"]
                        messages.append(tool_message)
                        pending_events.append({
                            "event_type": "tool_result",
                            "payload": {
                                "tool_call_id": outcome.get("tool_call_id", ""),
                                "name": outcome.get("name", ""),
                                "result": result_data,
                            },
                            "llm_response_id": None,
                        })

                    # ── Auto-create assets for tool outputs ─────────
                    try:
                        async with AsyncSessionLocal() as _aa_db:
                            await sink.record_assets(
                                orchestrated_results,
                            )
                    except Exception as _aa_exc:
                        logger.warning(
                            "Auto-asset creation failed (non-fatal): %s", _aa_exc,
                        )

                # ── Incremental event persistence ───────────────────
                try:
                    async with AsyncSessionLocal() as _cp_db:
                        persisted_event_count = await sink.persist_pending_events(
                            _cp_db, pending_events, persisted_event_count,
                        )
                except Exception as _cp_exc:
                    logger.warning(
                        "Incremental persist failed (non-fatal): %s", _cp_exc,
                    )

                # ── Stuck detector ──────────────────────────────────
                _stuck_check = {"stuck": False}
                if tool_calls:
                    _stuck_check = detect_tool_round_stuck(tool_calls, _session_key)
                else:
                    has_error = bool(result.get("error"))
                    is_empty = not result.get("content") and not result.get("tool_calls")
                    _stuck_check = detect_stuck(
                        tool_name=None,
                        tool_args=None,
                        error_text=str(result.get("error"))[:100] if has_error else None,
                        is_empty_response=is_empty,
                        session_key=_session_key,
                    )
                if _stuck_check.get("stuck"):
                    logger.warning(
                        "stuck_detector break: %s", _stuck_check["reason"],
                    )
                    yield self._sse("error", _stuck_check["reason"])
                    break

                # ── Diminishing returns check ───────────────────────
                _tokens_after = (
                    sum(max(estimate_tokens([m]), 0) for m in messages[-10:])
                    if messages else 0
                )
                budget_tracker.record_round(
                    _budget_session_key,
                    _tool_round_tokens_before,
                    _tokens_after,
                )
                _tool_round_tokens_before = _tokens_after
                _should_stop, _stop_reason = budget_tracker.should_stop(
                    _budget_session_key,
                )
                if _should_stop:
                    logger.warning(
                        "diminishing_returns break: %s", _stop_reason,
                    )
                    try:
                        async with AsyncSessionLocal() as _diag_db:
                            await sink.record_event(
                                _diag_db, "diminishing_stop",
                                {"reason": _stop_reason, "round": _round + 1},
                            )
                    except Exception:
                        logger.debug("Failed to record diminishing_stop event")
                    action = await self._decide_stop_action(messages)
                    logger.info("[DIAG] LLM stop decision: %s", action)
                    if action == "continue":
                        budget_tracker.reset(_budget_session_key)
                        continue
                    async for chunk in self._generate_final_summary(messages, tool_events, timeline, full):
                        yield chunk
                    break

                # ── Checkpoint: save execution state after each round ──
                if self.policy.enable_checkpointer:
                    _cp_id = PostgresCheckpointSaver.new_checkpoint_id()
                    _channel_vals = {
                        "messages": messages,
                        "tool_events": tool_events,
                        "timeline": timeline,
                        "pending_events": pending_events,
                        "event_round": event_round,
                        "persisted_event_count": persisted_event_count,
                    }
                    try:
                        async with AsyncSessionLocal() as _ck_db:
                            _saver = PostgresCheckpointSaver()
                            await _saver.put(
                                _ck_db,
                                conversation_id=self.conversation_id,
                                owner_id=self.owner_id,
                                checkpoint_id=_cp_id,
                                step=_round + 1,
                                channel_values=_channel_vals,
                                parent_checkpoint_id=_last_checkpoint_id,
                            )
                        _last_checkpoint_id = _cp_id
                        logger.info(
                            "Checkpoint saved: conv=%d step=%d cp=%s",
                            self.conversation_id, _round + 1, _cp_id,
                        )
                    except Exception as _ck_exc:
                        logger.warning(
                            "Checkpoint save failed (non-fatal): %s", _ck_exc,
                        )
            else:
                # ── Tool rounds exhausted → final summary ───────────
                async for chunk in self._generate_final_summary(messages, tool_events, timeline, full):
                    yield chunk

        except (Exception, asyncio.CancelledError) as exc:
            logger.info(
                "[DIAG] ToolLoopRuntime EXCEPTION %s: %s",
                type(exc).__name__, str(exc)[:300],
            )
            if not isinstance(exc, asyncio.CancelledError):
                await sink.record_failure(
                    "chat", "tool_loop",
                    type(exc).__name__, str(exc),
                )
                try:
                    yield self._sse("error", str(exc))
                except GeneratorExit:
                    _disconnected = True

        # ── Finally: persist + post-turn hooks ──────────────────────
        if not _disconnected:
            try:
                logger.info("[DIAG] ToolLoopRuntime starting final persist")
                async with AsyncSessionLocal() as s2:
                    msg_id = await sink.persist_assistant(
                        s2, "".join(full) if full else "",
                        thinking_parts, tool_events, timeline,
                        usage=emitter.usage_data,
                    )
                    # Ensure assistant_msg event for final content
                    if msg_id and full:
                        clean_content = final_clean_content("".join(full))
                        has_pending = any(
                            e["event_type"] == "assistant_msg"
                            and clean_content[:200] in str(e["payload"].get("content", ""))
                            for e in pending_events
                        )
                        if not has_pending:
                            _final_rid = f"round_{event_round}"
                            event_round += 1
                            pending_events.append({
                                "event_type": "assistant_msg",
                                "payload": {"content": clean_content},
                                "llm_response_id": _final_rid,
                            })
                    await sink.persist_pending_events(
                        s2, pending_events, persisted_event_count,
                    )
                    await sink.run_post_turn_hooks(
                        s2, messages, tool_events, timeline,
                    )
            except Exception as exc:
                logger.warning(
                    "ToolLoopRuntime final persist failed (non-fatal): %s", exc,
                )

        if not _disconnected:
            try:
                yield b"data: [DONE]\n\n"
            except GeneratorExit:
                logger.debug("GeneratorExit during final SSE yield (client disconnected)")
        logger.info("[DIAG] ToolLoopRuntime EXIT")

    async def _decide_stop_action(self, messages: list[dict]) -> str:
        """Ask the LLM whether to continue tool calls or reply to the user.

        Returns ``"continue"`` (keep running tools) or ``"stop"``
        (exit the tool loop and let the agent reply naturally).
        """
        recent = messages[-6:] if len(messages) > 6 else messages
        context_lines = []
        for m in recent:
            role = m.get("role", "unknown")
            content = (m.get("content") or "")[:300]
            tool_calls = m.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", tc)
                    context_lines.append(f"[{role}] call tool: {fn.get('name', '?')}")
            if content:
                context_lines.append(f"[{role}] {content}")
        context_str = "\n".join(context_lines[-15:])
        prompt = [
            {"role": "system", "content": "You are a conversation router. Based on the tool execution results below, decide what to do next. Reply with JSON: {\"action\": \"continue\" | \"stop\"}. continue = still need more tool calls to complete the user's request. stop = tools have done enough, stop and reply to the user."},
            {"role": "user", "content": f"Recent conversation:\n{context_str}\n\nDecision (JSON):"},
        ]
        try:
            result = await chat_with_degradation_chain(
                prompt, self.profile_key, tools=None,
                conversation_id=self.conversation_id,
            )
            raw = result.get("content", "")
            import re
            m = re.search(r'"action"\s*:\s*"(continue|stop)"', raw)
            if m:
                return m.group(1)
        except Exception as exc:
            logger.warning("LLM stop decision failed (non-fatal): %s", exc)
        return "stop"

    async def _generate_final_summary(
        self,
        messages: list[dict],
        tool_events: list[dict],
        timeline: list[dict],
        full: list[str],
    ):
        """Generate a final summary when tool rounds run out or are stopped early."""
        if not self.policy.allow_final_summary_fallback:
            return
        logger.info("[DIAG] Generating final summary fallback")
        _final_summary = await chat_with_degradation_chain(
            messages, self.profile_key, tools=None,
            conversation_id=self.conversation_id,
        )
        if _final_summary.get("content"):
            final_text = str(_final_summary["content"])
            full.clear()
            full.append(final_text)
            timeline.append({"type": "text", "content": final_text})
            yield self._sse("token", final_text)
        elif _final_summary.get("error"):
            yield self._sse("error", _final_summary["error"])

    @staticmethod
    def _sse(event_type: str, content: str) -> bytes:
        """Format an SSE data: frame."""
        return (
            f"data: {json.dumps({'type': event_type, 'content': content}, ensure_ascii=False)}\n\n"
        ).encode("utf-8")

    @staticmethod
    def _j_sse(obj: dict) -> bytes:
        """Format a JSON dict as an SSE data: frame."""
        return (
            f"data: {json.dumps(obj, ensure_ascii=False, default=str)}\n\n"
        ).encode("utf-8")
