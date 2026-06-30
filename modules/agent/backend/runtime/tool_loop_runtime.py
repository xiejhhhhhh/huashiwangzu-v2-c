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
import time

from app.database import AsyncSessionLocal

from .._utils import j as _j
from .._utils import references_from_tool_events, tool_calls_for_history
from ..engine.budget_allocator import (
    RESERVED_OUTPUT_TOKENS,
    _group_projected_messages,
    estimate_one_message,
    estimate_tokens,
    get_effective_context_budget,
)
from ..engine.engine import (
    chat_stream_with_degradation_chain,
    chat_with_degradation_chain,
    get_budget_tracker,
    get_orchestrator,
)
from ..engine.stuck_detector import detect_stuck
from ..engine.stuck_detector import reset as reset_stuck
from ..prompt_seeds import FINAL_SUMMARY_KEY, STOP_DECISION_KEY
from ..services import tool_discovery
from ..services.action_policy import check_action_allowed
from ..services.model_client import final_clean_content, parse_inline_tool_calls, recover_tool_calls
from ..services.runtime_prompt_provider import get_system_prompt as get_runtime_system_prompt
from .checkpointer import PostgresCheckpointSaver
from .content_gate import TOOL_INTENT_RETRY_MESSAGE, looks_like_unfinished_tool_intent, user_safe_error_message
from .runtime_policy import RuntimePolicy
from .stream_emitter import StreamEmitter
from .stream_proxy import StreamProxy, StreamSegment
from .task_sink import RuntimeTaskSink

logger = logging.getLogger("v2.agent").getChild("runtime.tool_loop")


_USAGE_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def _merge_usage(target: dict, usage: dict | None) -> None:
    if not isinstance(usage, dict):
        return
    for key in _USAGE_KEYS:
        value = usage.get(key, 0)
        if isinstance(value, (int, float)):
            target[key] = int(target.get(key, 0) or 0) + int(value)


def _has_token_usage(usage: dict | None) -> bool:
    return bool(isinstance(usage, dict) and any(int(usage.get(key, 0) or 0) for key in _USAGE_KEYS))


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
        suppress_thinking: bool = False,
        user_role: str = "viewer",
        initial_usage: dict | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.owner_id = owner_id
        self.profile_key = profile_key
        self.policy = policy or RuntimePolicy.default()
        self.suppress_thinking = suppress_thinking
        self.user_role = user_role
        self.initial_usage = initial_usage or {}

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
            _work_start_time = time.time()
            yield self._j_sse({"type": "work_start", "started_at": _work_start_time})
            reset_stuck(_session_key)
            budget_tracker = get_budget_tracker()
            budget_tracker.reset(_budget_session_key)

            _tool_round_tokens_before = 0
            _tool_intent_retry_count = 0
            # Accumulate usage across all model calls in this turn
            _accumulated_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "model_call_count": 0}
            _max_single_call_prompt_tokens = 0
            _merge_usage(_accumulated_usage, self.initial_usage)
            emitter = StreamEmitter()

            _model_call_count = 0
            # Stable turn identity: use the latest persisted user event id.
            # Counts can be reused after rollback/edit flows; event ids cannot.
            _turn_ordinal = 0
            try:
                from sqlalchemy import func as _sf
                from sqlalchemy import select as _ss

                from ..models import AgentEvent
                async with AsyncSessionLocal() as _turn_db:
                    _tr = await _turn_db.execute(
                        _ss(_sf.max(AgentEvent.id)).select_from(AgentEvent)
                        .where(AgentEvent.conversation_id == self.conversation_id,
                               AgentEvent.event_type == "user_msg")
                    )
                    _turn_ordinal = _tr.scalar() or 0
            except Exception:
                logger.warning("Failed to compute turn ordinal, using 0")

            for _round in range(_resume_from_step, self.policy.max_tool_rounds):
                # Y1: reset full each round to avoid cross-round accumulation
                full = []
                logger.info(
                    "[DIAG] ToolLoopRuntime round %d/%d",
                    _round + 1, self.policy.max_tool_rounds,
                )

                # ── Round-level budget guard ───────────────────────────
                _guard_t0 = time.monotonic()
                _effective_budget, _budget_source = get_effective_context_budget(self.profile_key)
                _messages_tokens = sum(estimate_one_message(m) for m in messages)
                _input_budget = max(_effective_budget - RESERVED_OUTPUT_TOKENS - 1024, 0)
                if _messages_tokens > _input_budget and len(messages) > 1:
                    _before = len(messages)
                    _system_messages = [m for m in messages if m.get("role") == "system"]
                    _history_messages = [m for m in messages if m.get("role") != "system"]
                    _tail_groups = _group_projected_messages(_history_messages)
                    _system_tokens = sum(estimate_one_message(m) for m in _system_messages)
                    _remaining = max(_input_budget - _system_tokens, 0)

                    # Reserve the latest user goal before filling with recent
                    # tool groups, otherwise a large result can evict the goal.
                    _latest_user_idx = next(
                        (idx for idx in range(len(_tail_groups) - 1, -1, -1)
                         if any(m.get("role") == "user" for m in _tail_groups[idx])),
                        None,
                    )
                    _selected: dict[int, list[dict]] = {}
                    _used = 0
                    if _latest_user_idx is not None:
                        _pinned = _tail_groups[_latest_user_idx]
                        _selected[_latest_user_idx] = _pinned
                        _used += sum(estimate_one_message(m) for m in _pinned)

                    for _idx in range(len(_tail_groups) - 1, -1, -1):
                        if _idx in _selected:
                            continue
                        _g = _tail_groups[_idx]
                        _gt = sum(estimate_one_message(m) for m in _g)
                        if _used + _gt <= _remaining:
                            _selected[_idx] = _g
                            _used += _gt

                    _kept = list(_system_messages)
                    for _idx in sorted(_selected):
                        _g = _selected[_idx]
                        _kept.extend(_g)
                    messages = _kept
                    _after = len(messages)
                    logger.info(
                        "[BUDGET_GUARD] round=%d messages trimmed: %d→%d, tokens=%d, budget=%d",
                        _round, _before, _after, _messages_tokens, _input_budget,
                    )
                logger.debug("[BUDGET_GUARD] round=%d guard done in %dms",
                             _round, round((time.monotonic() - _guard_t0) * 1000))

                # ── Streaming model call for tool decisions ─────────
                _decision_t0 = time.monotonic()
                if self.policy.enable_single_pass_streaming_tools:
                    result = {}
                    async for stream_item in self._stream_until_tool_or_done(
                        messages,
                        tools,
                        full,
                        thinking_parts,
                        timeline,
                        emitter,
                    ):
                        if isinstance(stream_item, dict) and stream_item.get("type") == "_stream_result":
                            result = stream_item.get("result") or {}
                        else:
                            yield stream_item
                else:
                    result = await chat_with_degradation_chain(
                        messages,
                        self.profile_key,
                        tools,
                        conversation_id=self.conversation_id,
                    )
                _decision_ms = round((time.monotonic() - _decision_t0) * 1000)
                logger.info(
                    "[DIAG] ToolLoopRuntime chat returned tool_calls=%s profile=%s error=%s decision_ms=%d",
                    len(result.get("tool_calls") or []),
                    self.profile_key,
                    bool(result.get("error")),
                    _decision_ms,
                )

                # ── Accumulate usage from each model call ─────────────
                _model_call_count += 1
                _accumulated_usage["model_call_count"] = _model_call_count
                _call_usage = result.get("usage") or {}
                _merge_usage(_accumulated_usage, _call_usage)
                _single_prompt = _call_usage.get("prompt_tokens", 0)
                if _single_prompt > _max_single_call_prompt_tokens:
                    _max_single_call_prompt_tokens = _single_prompt

                if result.get("error"):
                    error_msg = str(result["error"])
                    logger.warning("ToolLoopRuntime model error: %s", error_msg)
                    yield self._sse("error", user_safe_error_message(error_msg))
                    break

                if result.get("thinking") and not self.suppress_thinking:
                    thinking = str(result["thinking"])
                    # 清洗泄漏到思考中的 XML 工具调用标记
                    clean_thinking, _ = parse_inline_tool_calls(thinking)
                    thinking_parts.append(clean_thinking)
                    timeline.append({"type": "thinking", "content": clean_thinking, "started_at": time.time()})
                    # 拆为小块分帧发送，前端自然拼接产生流式效果（无延时、不限速）
                    for i in range(0, len(clean_thinking), 10):
                        yield self._sse("thinking", clean_thinking[i:i + 10])
                elif self.suppress_thinking and (result.get("tool_calls") or result.get("finish_reason") == "tool_calls"):
                    # 思考被省略时，仍发一个占位提示，避免工作组空荡荡
                    placeholder = "（思考已省略）"
                    timeline.append({"type": "thinking", "content": placeholder, "started_at": time.time(), "duration_ms": 0})
                    yield self._sse("thinking", placeholder)

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
                    if self.policy.enable_single_pass_streaming_tools:
                        break
                    retry_tool_intent = None
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
                        suppress_thinking=self.suppress_thinking,
                    ):
                        if isinstance(chunk, dict) and chunk.get("type") == "_inline_tool_calls":
                            inline_from_stream = chunk.get("tool_calls", [])
                        elif isinstance(chunk, dict) and chunk.get("type") == "_retry_tool_intent_contract":
                            retry_tool_intent = chunk
                        else:
                            yield chunk
                    if retry_tool_intent:
                        if emitter.usage_data:
                            for _k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                                _v = emitter.usage_data.get(_k, 0)
                                if isinstance(_v, (int, float)):
                                    _accumulated_usage[_k] = (_accumulated_usage.get(_k, 0) or 0) + int(_v)
                        _tool_intent_retry_count += 1
                        if _tool_intent_retry_count <= 1:
                            messages.append({
                                "role": "user",
                                "content": retry_tool_intent.get("message") or "Regenerate with a real tool call or a direct answer.",
                            })
                            timeline.append({
                                "type": "contract_retry",
                                "content": retry_tool_intent.get("content", ""),
                                "started_at": time.time(),
                            })
                            logger.info(
                                "[DIAG] ToolLoopRuntime retrying unfinished tool-intent reply",
                            )
                            continue
                        yield self._sse("error", "模型表示需要查询资料，但连续没有发起工具调用。")
                        break
                    if inline_from_stream:
                        tool_calls = inline_from_stream
                        # ── Accumulate usage for inline case too ──
                        if emitter.usage_data:
                            for _k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                                _v = emitter.usage_data.get(_k, 0)
                                if isinstance(_v, (int, float)):
                                    _accumulated_usage[_k] = (_accumulated_usage.get(_k, 0) or 0) + int(_v)
                        logger.info(
                            "[DIAG] ToolLoopRuntime re-entering with %d inline calls",
                            len(tool_calls),
                        )
                    else:
                        # ── Accumulate usage BEFORE break ──────────
                        if emitter.usage_data:
                            for _k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                                _v = emitter.usage_data.get(_k, 0)
                                if isinstance(_v, (int, float)):
                                    _accumulated_usage[_k] = (_accumulated_usage.get(_k, 0) or 0) + int(_v)
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
                _tool_call_times: dict[str, float] = {}  # tool_call_id → start timestamp
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
                    _tool_call_times[tool_call_id] = time.time()
                    call_event = {
                        "type": "tool_call", "name": name,
                        "tool_call_id": tool_call_id,
                        "arguments": args, "started_at": time.time(),
                    }
                    tool_events.append(call_event)
                    timeline.append(call_event)
                    yield self._j_sse(call_event)

                # ── ToolGate: validate tool names before execution ──
                from .tool_gate import format_retry_message, validate_tool_calls
                _valid_tools, _invalid_names = validate_tool_calls(parsed_tools, tools, role=self.user_role)
                if _invalid_names:
                    logger.warning(
                        "[ToolGate] %d invalid tool(s) rejected: %s",
                        len(_invalid_names), _invalid_names,
                    )
                    invalid_tools = [tool for tool in parsed_tools if tool not in _valid_tools]
                    for tool in invalid_tools:
                        tool_result = {
                            "error": "invalid_tool_name",
                            "tool_name": tool.get("name", ""),
                            "message": format_retry_message(_invalid_names),
                        }
                        result_event = {
                            "type": "tool_result",
                            "name": tool.get("name", ""),
                            "tool_call_id": tool.get("tool_call_id", ""),
                            "result": tool_result,
                            "started_at": time.time(),
                            "duration_ms": round((time.time() - _tool_call_times.get(tool.get("tool_call_id", ""), time.time())) * 1000),
                        }
                        tool_events.append(result_event)
                        timeline.append(result_event)
                        yield self._j_sse(result_event)
                        tool_message = {
                            "role": "tool",
                            "name": tool.get("name", ""),
                            "content": _j(tool_result),
                        }
                        if tool.get("tool_call_id"):
                            tool_message["tool_call_id"] = tool["tool_call_id"]
                        messages.append(tool_message)
                        pending_events.append({
                            "event_type": "tool_result",
                            "payload": {
                                "tool_call_id": tool.get("tool_call_id", ""),
                                "name": tool.get("name", ""),
                                "result": tool_result,
                                "duration_ms": result_event["duration_ms"],
                            },
                            "llm_response_id": None,
                        })
                    messages.append({
                        "role": "user",
                        "content": format_retry_message(_invalid_names),
                    })
                    yield self._sse(
                        "tool_gate_retry",
                        format_retry_message(_invalid_names),
                    )
                    continue  # next tool round with retry message
                parsed_tools = _valid_tools

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
                        caller_role=self.user_role,
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
                        "tool_call_id": tool["tool_call_id"],
                        "result": tool_result,
                        "started_at": time.time(),
                        "duration_ms": round((time.time() - _tool_call_times.get(tool["tool_call_id"], time.time())) * 1000),
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
                            "duration_ms": round((time.time() - _tool_call_times.get(tool["tool_call_id"], time.time())) * 1000),
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
                        effective_name = (
                            str((tool.get("args") or {}).get("name") or tool["name"])
                            if tool["name"] == "skill_use"
                            else tool["name"]
                        )
                        async with AsyncSessionLocal() as _pol_db:
                            pol = await check_action_allowed(
                                _pol_db, effective_name, AGENT_CODE,
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
                                tool["args"], self.user_role,
                            )
                        elif tool["name"] == "skill_describe":
                            return await tool_discovery.handle_skill_describe(
                                tool["args"], self.user_role,
                            )
                        elif tool["name"] == "skill_use":
                            return await tool_discovery.handle_skill_use(
                                tool["args"],
                                caller=f"user:{self.owner_id}",
                                caller_role=self.user_role,
                            )
                        else:
                            from app.services.module_registry import call_capability
                            module_key, action = tool_discovery.parse_tool_name(
                                tool["name"],
                            )
                            caller = f"user:{self.owner_id}" if self.owner_id else "system:tool-loop"
                            return await call_capability(
                                module_key, action, tool.get("args") or tool.get("arguments", {}),
                                caller=caller,
                                caller_role=self.user_role,
                            )

                    orchestrator_tools = [
                        {
                            "name": t["name"],
                            "tool_call_id": t["tool_call_id"],
                            "args": t["args"],
                        }
                        for t in fast_tools
                    ]
                    _tool_batch_t0 = time.monotonic()
                    orchestrated_results = await orchestrator.execute_batch(
                        orchestrator_tools, _tool_execute_fn,
                    )
                    logger.info(
                        "[DIAG] ToolLoopRuntime fast tool batch count=%d duration_ms=%d",
                        len(orchestrator_tools),
                        round((time.monotonic() - _tool_batch_t0) * 1000),
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
                            "tool_call_id": outcome.get("tool_call_id", ""),
                            "result": result_data,
                            "started_at": time.time(),
                            "duration_ms": round((time.time() - _tool_call_times.get(outcome.get("tool_call_id", ""), time.time())) * 1000),
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
                                "duration_ms": round((time.time() - _tool_call_times.get(outcome.get("tool_call_id", ""), time.time())) * 1000),
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
                    if self.policy.llm_stop_decision_enabled:
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
                    yield self._sse("error", user_safe_error_message(exc))
                except GeneratorExit:
                    _disconnected = True

        # ── Finally: persist + post-turn hooks ──────────────────────
        if not _disconnected:
            try:
                logger.info("[DIAG] ToolLoopRuntime starting final persist")
                async with AsyncSessionLocal() as s2:
                    _usage = dict(_accumulated_usage) if _has_token_usage(_accumulated_usage) else (dict(emitter.usage_data) if emitter.usage_data else {})
                    _usage["model_call_count"] = _model_call_count
                    _usage["max_single_call_prompt_tokens"] = _max_single_call_prompt_tokens
                    work_duration_ms = round((time.time() - _work_start_time) * 1000)
                    _usage["work_duration_ms"] = work_duration_ms
                    _usage["work_duration_sec"] = round(work_duration_ms / 1000)
                    timeline.append({
                        "type": "work_summary",
                        "duration_ms": work_duration_ms,
                        "duration_sec": round(work_duration_ms / 1000, 3),
                        "started_at": time.time(),
                    })
                    yield self._j_sse({
                        "type": "work_done",
                        "duration_ms": work_duration_ms,
                        "duration_sec": round(work_duration_ms / 1000, 3),
                    })

                    # round_usage 下移到 persist_assistant 判断后（只在 msg_id 存在时下发）

                    # ── 计算每段思考耗时，写入 timeline ──────────
                    _work_end = time.time()
                    for _idx, _entry in enumerate(timeline):
                        if _entry.get("type") != "thinking" or "duration_ms" in _entry:
                            continue
                        _start = _entry.get("started_at")
                        if not _start:
                            continue
                        # 找下一个有 started_at 的条目
                        _next_time = _work_end
                        for _nx in timeline[_idx + 1:]:
                            if _nx.get("started_at"):
                                _next_time = _nx["started_at"]
                                break
                        _entry["duration_ms"] = max(0, round((_next_time - _start) * 1000))

                    # ── 计算未覆盖时间（网络/模型调度开销） ─────
                    _accounted = sum(
                        e.get("duration_ms", 0)
                        for e in timeline
                        if e.get("type") in ("thinking", "tool_result")
                    )
                    _overhead = work_duration_ms - _accounted
                    if _overhead > 500:  # 超过 0.5 秒的差额才显示
                        timeline.insert(0, {
                            "type": "schedule_overhead",
                            "label": "响应等待",
                            "duration_ms": _overhead,
                            "started_at": time.time(),
                        })

                    _round_references = references_from_tool_events(tool_events)
                    msg_id = await sink.persist_assistant(
                        s2, "".join(full) if full else "",
                        thinking_parts, tool_events, timeline,
                        usage=_usage,
                    )

                    if msg_id:
                        if _has_token_usage(_usage):
                            yield self._j_sse({"type": "round_usage", **_usage})
                        if _round_references:
                            yield self._j_sse({"type": "references", "references": _round_references})
                    else:
                        yield self._j_sse({"type": "assistant_empty", "reason": "empty_after_clean"})

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
                                "payload": {"content": clean_content, "usage": _usage},
                                "llm_response_id": _final_rid,
                            })
                    await sink.persist_pending_events(
                        s2, pending_events, persisted_event_count,
                    )

                    # ── Completion evidence ──────────────────────
                    try:
                        _completion_evidence = await sink.generate_completion_evidence(
                            tool_events,
                            [tr for tr in tool_events if tr.get("type") == "tool_result"],
                        )
                        if _completion_evidence:
                            await sink.record_event(
                                s2, "completion_evidence",
                                {"evidence": _completion_evidence, "turn": _turn_ordinal},
                                llm_response_id=None,
                            )
                    except Exception as _ce_exc:
                        logger.warning("Completion evidence failed (non-fatal): %s", _ce_exc)

                    # ── Record trajectory (idempotent upsert) ────
                    _turn_usage = _usage if isinstance(_usage, dict) else {}
                    _thinking_lvl = None
                    for _te in timeline or []:
                        if _te.get("type") == "thinking_diag":
                            _thinking_lvl = _te.get("level")
                            break
                    _tool_success = sink.check_tool_success(tool_events)
                    _trajectory_result: dict = {}
                    try:
                        _trajectory_result = await sink.record_trajectory(
                            s2,
                            turn_index=_turn_ordinal,
                            tool_calls=[tc for tc in tool_events if tc.get("type") == "tool_call"],
                            tool_results=[tr for tr in tool_events if tr.get("type") == "tool_result"],
                            assistant_response="".join(full) if full else "",
                            thinking_level=_thinking_lvl,
                            error_occurred=not _tool_success,
                            duration_ms=work_duration_ms,
                            token_count=_turn_usage.get("prompt_tokens", 0) + _turn_usage.get("completion_tokens", 0),
                        )
                    except Exception as _tr_exc:
                        logger.warning("Trajectory recording failed (non-fatal): %s", _tr_exc)

                    await sink.run_post_turn_hooks(
                        s2, messages, tool_events, timeline,
                        trajectory_id=(
                            _trajectory_result.get("id")
                            if _trajectory_result.get("recorded") else None
                        ),
                        turn_index=_turn_ordinal,
                    )

                    # ── 提炼上下文变量 ──────────────────────────
                    if tool_events:
                        try:
                            from ..engine.context_vars import extract_context_vars
                            from ..models import AgentConversation
                            _new_vars = extract_context_vars(tool_events)
                            if _new_vars:
                                _conv = await s2.get(AgentConversation, self.conversation_id)
                                if _conv:
                                    _merged = dict(_conv.context_vars or {})
                                    _merged.update(_new_vars)
                                    _conv.context_vars = _merged
                                    await s2.commit()
                                    logger.info(
                                        "[DIAG] context_vars updated: %s",
                                        str(list(_new_vars.keys())),
                                    )
                        except Exception as _cv_exc:
                            logger.warning("context_vars extraction failed (non-fatal): %s", _cv_exc)
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

    async def _stream_until_tool_or_done(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        full: list[str],
        thinking_parts: list[str],
        timeline: list[dict],
        emitter: StreamEmitter,
    ):
        """Stream one model turn until it finishes or emits complete tool calls."""
        proxy = StreamProxy(emitter)
        segment: StreamSegment | None = None
        content_parts: list[str] = []
        thinking_text = ""
        usage_data: dict | None = None
        finish_reason = "stop"

        async for event in chat_stream_with_degradation_chain(
            messages,
            self.profile_key,
            tools,
            conversation_id=self.conversation_id,
        ):
            event_type = event.get("type")
            content = str(event.get("content") or "")
            if event_type in ("token", "content") and content:
                if segment is None:
                    segment = proxy.new_segment("assistant")
                    start_event = proxy.start(segment)
                    if start_event:
                        yield start_event
                content_parts.append(content)
                full.append(content)
                timeline.append({"type": "text", "content": content, "started_at": time.time()})
                delta_event = proxy.delta(segment, content)
                if delta_event:
                    yield delta_event
            elif event_type == "thinking" and content:
                from ..services.model_client import parse_inline_tool_calls
                clean, _ = parse_inline_tool_calls(content)
                thinking_text += clean
                if not self.suppress_thinking:
                    thinking_parts.append(clean)
                    timeline.append({"type": "thinking", "content": clean, "started_at": time.time()})
                    yield self._sse("thinking", clean)
            elif event_type == "tool_call":
                if segment is not None:
                    rollback_event = proxy.rollback(segment, "tool_call_detected")
                    if rollback_event:
                        yield rollback_event
                    full.clear()
                yield {
                    "type": "_stream_result",
                    "result": {
                        "content": "".join(content_parts),
                        "thinking": thinking_text,
                        "tool_calls": event.get("tool_calls") or [],
                        "finish_reason": "tool_calls",
                        "usage": usage_data or {},
                    },
                }
                return
            elif event_type == "usage":
                data = event.get("data") or event.get("usage") or {}
                if isinstance(data, dict):
                    usage_data = data
                    emitter.usage_data = data
            elif event_type == "degradation" and content:
                yield self._sse("thinking", content)
            elif event_type == "error" and content:
                yield {"type": "_stream_result", "result": {"error": content, "content": content}}
                return
            elif event_type == "done":
                done_usage = event.get("usage")
                if isinstance(done_usage, dict):
                    usage_data = done_usage
                    emitter.usage_data = done_usage
                finish_reason = event.get("finish_reason") or finish_reason
                break

        raw_content = "".join(content_parts)
        try:
            clean_content, inline_calls = parse_inline_tool_calls(raw_content)
        except Exception as exc:
            logger.warning("parse_inline_tool_calls failed during streaming decision: %s", exc)
            clean_content, inline_calls = raw_content, []
        if inline_calls:
            if segment is not None:
                rollback_event = proxy.rollback(segment, "inline_tool_call_detected", replacement=clean_content)
                if rollback_event:
                    yield rollback_event
                full.clear()
                if clean_content:
                    full.append(clean_content)
            yield {
                "type": "_stream_result",
                "result": {
                    "content": clean_content,
                    "thinking": thinking_text,
                    "tool_calls": inline_calls,
                    "finish_reason": "tool_calls",
                    "usage": usage_data or {},
                },
            }
            return

        if looks_like_unfinished_tool_intent(clean_content):
            if segment is not None:
                rollback_event = proxy.rollback(segment, "unfinished_tool_intent")
                if rollback_event:
                    yield rollback_event
            full.clear()
            yield {
                "type": "_stream_result",
                "result": {
                    "content": clean_content,
                    "error": TOOL_INTENT_RETRY_MESSAGE,
                    "usage": usage_data or {},
                },
            }
            return

        if segment is not None:
            commit_event = proxy.commit(segment)
            if commit_event:
                yield commit_event
        yield {
            "type": "_stream_result",
            "result": {
                "content": clean_content,
                "thinking": thinking_text,
                "tool_calls": [],
                "finish_reason": finish_reason,
                "usage": usage_data or {},
            },
        }

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
        async with AsyncSessionLocal() as prompt_db:
            stop_prompt = await get_runtime_system_prompt(prompt_db, STOP_DECISION_KEY)
        prompt = [
            {"role": "system", "content": stop_prompt},
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
        logger.info("[DIAG] Generating final summary fallback (streaming)")
        _summary_t0 = time.monotonic()
        async with AsyncSessionLocal() as prompt_db:
            final_summary_prompt = await get_runtime_system_prompt(prompt_db, FINAL_SUMMARY_KEY)
        summary_messages = messages + [{
            "role": "user",
            "content": final_summary_prompt,
        }]
        summary_parts: list[str] = []
        emitter = StreamEmitter()
        proxy = StreamProxy(emitter)
        segment: StreamSegment | None = None
        async for event in chat_stream_with_degradation_chain(
            summary_messages, self.profile_key, tools=None,
            conversation_id=self.conversation_id,
        ):
            event_type = event.get("type")
            content = str(event.get("content") or "")
            if event_type in ("token", "content") and content:
                summary_parts.append(content)
                if segment is None:
                    segment = proxy.new_segment("assistant")
                    start_event = proxy.start(segment)
                    if start_event:
                        yield start_event
                delta_event = proxy.delta(segment, content)
                if delta_event:
                    yield delta_event
            elif event_type == "thinking" and content:
                from ..services.model_client import parse_inline_tool_calls
                clean, _ = parse_inline_tool_calls(content)
                timeline.append({"type": "thinking", "content": clean})
                yield self._sse("thinking", clean)
            elif event_type == "error" and content:
                yield self._sse("error", content)
            elif event_type == "done":
                break
        logger.info(
            "[DIAG] Final summary completed duration_ms=%d parts=%d",
            round((time.monotonic() - _summary_t0) * 1000),
            len(summary_parts),
        )

        # ── Clean inline XML from final summary content before display ──
        if summary_parts:
            raw = "".join(summary_parts)
            clean, inline_calls = parse_inline_tool_calls(raw)
            if clean != raw:
                logger.info(
                    "[DIAG] Final summary cleaned: %d chars → %d chars",
                    len(raw), len(clean),
                )
                if segment is not None:
                    rollback_event = proxy.rollback(segment, "summary_cleaned", replacement=clean)
                    if rollback_event:
                        yield rollback_event
            final_text = clean.strip()

            if not final_text and inline_calls:
                final_text = self._fallback_answer_from_tool_events(tool_events)
            if final_text:
                full.append(final_text)
                timeline.append({"type": "text", "content": final_text})
                if segment is not None and not segment.closed:
                    commit_event = proxy.commit(segment)
                    if commit_event:
                        yield commit_event
                elif segment is None:
                    yield self._sse("token", final_text)

    def _fallback_answer_from_tool_events(self, tool_events: list[dict]) -> str:
        """Build a minimal user-visible answer when final summary emits only tool calls."""
        snippets: list[str] = []
        for event in reversed(tool_events):
            if event.get("type") != "tool_result":
                continue
            result = event.get("result")
            if not isinstance(result, dict):
                continue
            candidates = []
            if isinstance(result.get("results"), list):
                candidates = result.get("results") or []
            elif isinstance(result.get("data"), dict) and isinstance(result["data"].get("results"), list):
                candidates = result["data"].get("results") or []
            for item in candidates[:3]:
                if not isinstance(item, dict):
                    continue
                text = item.get("snippet") or item.get("text") or item.get("title") or ""
                if text:
                    snippets.append(str(text).strip())
            if snippets:
                break
        if not snippets:
            return "已完成检索，但模型未能生成最终摘要。请稍后重试。"
        joined = "\n".join(f"- {s}" for s in snippets[:3])
        return "根据已检索到的结果，相关信息如下：\n" + joined

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
