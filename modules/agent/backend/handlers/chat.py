"""Chat endpoint handler for agent module.

Contains: handle_chat (the complete POST /api/agent/chat flow),
_yield_final_stream, and helper functions.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.module_registry import call_capability

from ..init_db import (
    ensure_default_prompts,
    ensure_timeline_column,
    ensure_user_profile,
    update_existing_prompts,
    ensure_event_table,
    ensure_processing_column,
)
from 事件存储 import record_event
from .. import conversation_service as conv_svc
from .. import tool_discovery
from 引擎 import 装配上下文, chat_with_degradation_chain, chat_stream_with_degradation_chain
from 粘滞检测 import 检测粘滞, 重置 as 重置粘滞
from ..model_client import recover_tool_calls, parse_inline_tool_calls, final_clean_content
from ..action_policy import check_action_allowed, resolve_approval, list_pending_approvals

logger = logging.getLogger("v2.agent.router")

MAX_TOOL_ROUNDS = 5
EVOLVE_EVERY_N_MESSAGES = 3
SLOW_SKILL_NAMES: set[str] = {
    "image-gen__generate",
    "office-gen__convert",
}


def _j(obj) -> str:
    """json.dumps with datetime fallback."""
    return json.dumps(obj, ensure_ascii=False, default=str)


def _references_from_tool_events(events: list[dict]) -> list[dict]:
    refs: list[dict] = []
    for event in events:
        if event.get("type") != "tool_result":
            continue
        name = event.get("name", "tool") or ""
        result = event.get("result", {}) or {}
        inner = result
        if isinstance(inner, dict) and "data" in inner:
            inner = inner["data"]
        results_list = []
        if isinstance(inner, dict):
            results_list = inner.get("results", [])
        elif isinstance(inner, list):
            results_list = inner
        if results_list:
            for r_item in results_list:
                doc_name = r_item.get("document_name") or r_item.get("filename", "")
                page = r_item.get("page")
                excerpt = (r_item.get("text") or r_item.get("page_fusion", "") or "")[:240]
                title_parts = []
                if doc_name:
                    title_parts.append(doc_name)
                if page is not None:
                    title_parts.append(f"第{page}页")
                title = " ".join(title_parts) if title_parts else "知识库"
                refs.append({
                    "type": "knowledge",
                    "title": title,
                    "source": doc_name or "知识库",
                    "excerpt": excerpt,
                })
        else:
            refs.append({
                "type": "tool",
                "title": name,
                "source": name,
                "excerpt": _j(result)[:240],
            })
    return refs


def _tool_calls_for_history(tool_calls: list[dict]) -> list[dict]:
    normalized = []
    for item in tool_calls:
        fn = item.get("function", item)
        args = fn.get("arguments") or {}
        if not isinstance(args, str):
            args = _j(args)
        normalized.append({
            "id": item.get("id", ""),
            "type": item.get("type", "function"),
            "function": {
                "name": fn.get("name", ""),
                "arguments": args,
            },
        })
    return normalized


async def _yield_final_stream(
    kwargs: dict, full: list[str], thinking_parts: list[str],
    timeline: list[dict], profile_key: str = "deepseek-v4-flash",
    conversation_id: int | None = None,
):
    """Stream final content while checking for inline XML tool calls.

    Buffers token events, checks accumulated content for inline tool calls when
    streaming completes. If inline calls found, they are stripped from `full`
    and a special dict event {"type": "_inline_tool_calls", "tool_calls": [...]}
    is yielded as the last event (caller should re-enter tool loop). Otherwise,
    buffered events are flushed to the frontend normally.
    """
    logger.info("[DIAG] _yield_final_stream ENTER")
    event_count = 0
    token_buffer: list[tuple[str, str]] = []
    async for event in chat_stream_with_degradation_chain(kwargs["messages"], profile_key, kwargs.get("tools"), conversation_id=conversation_id):
        event_count += 1
        event_type = event.get("type")
        content = str(event.get("content") or "")
        logger.info("[DIAG] _yield_final_stream event #%d type=%s content_len=%d", event_count, event_type, len(content))
        if event_type == "thinking" and content:
            thinking_parts.append(content)
            timeline.append({"type": "thinking", "content": content})
            yield f"data: {json.dumps({'type': 'thinking', 'content': content}, ensure_ascii=False)}\n\n".encode("utf-8")
        elif event_type in ("token", "content") and content:
            full.append(content)
            timeline.append({"type": "text", "content": content})
            token_buffer.append((event_type, content))
        elif event_type == "error" and content:
            yield f"data: {json.dumps({'type': 'error', 'content': content}, ensure_ascii=False)}\n\n".encode("utf-8")
        elif event_type == "done":
            logger.info("[DIAG] _yield_final_stream got done event — stream ending")

    full_content = "".join(full)
    clean_content, inline_calls = parse_inline_tool_calls(full_content)
    if inline_calls:
        full.clear()
        full.append(clean_content)
        logger.info("[DIAG] _yield_final_stream found %d inline tool calls, re-entering tool loop", len(inline_calls))
        yield {"type": "_inline_tool_calls", "tool_calls": inline_calls}
        return

    for etype, econtent in token_buffer:
        yield f"data: {json.dumps({'type': 'token', 'content': econtent}, ensure_ascii=False)}\n\n".encode("utf-8")

    logger.info("[DIAG] _yield_final_stream EXIT after %d events — no inline calls", event_count)


async def handle_chat(payload, db: AsyncSession, user: User):
    """Handle POST /api/agent/chat — the complete chat flow with tool loop."""
    from ..models import AgentConversation

    # 确保默认数据、画像、表结构迁移和引擎事件表存在
    await ensure_timeline_column(db)
    await ensure_processing_column(db)
    await ensure_default_prompts(db)
    await update_existing_prompts(db)
    await ensure_user_profile(db, user.id)
    await ensure_event_table(db)

    # 持久化用户消息
    await conv_svc.add_message(db, user.id, payload.conversation_id, "user", payload.content)

    # 记录用户消息事件
    await record_event(db, payload.conversation_id, "user_msg", {"content": payload.content})

    # 引擎装配上下文（事件投影 + 三层提示词 + 动态预算 + Agent 配置）
    profile_key = payload.profile_key or "deepseek-v4-flash"
    agent_code = "erp_chat"
    messages, engine_diag = await 装配上下文(
        db, payload.conversation_id, payload.content,
        profile_key, user.id, agent_code=agent_code,
    )

    # 记录装配诊断事件
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
        logger.warning("记录装配诊断事件失败 (non-fatal): %s", diag_exc)

    # 记忆召回：自动检索用户相关记忆，注入 system prompt
    try:
        recall_result = await call_capability(
            "memory", "recall",
            {"query": payload.content, "limit": 5},
            caller=f"user:{user.id}",
            caller_role=user.role,
        )
        if recall_result and recall_result.get("success") and recall_result.get("data"):
            memories = recall_result["data"]
            if memories:
                memory_lines = []
                for m_item in memories:
                    text = m_item.get("text", "")
                    if text:
                        memory_lines.append(f"- {text}")
                if memory_lines:
                    memory_block = "你记得该用户之前的一些信息：\n" + "\n".join(memory_lines)
                    for msg in messages:
                        if msg["role"] == "system":
                            msg["content"] += "\n\n---\n\n" + memory_block
                            break
    except Exception as mem_recall_err:
        logger.warning("Memory recall failed (non-fatal): %s", mem_recall_err)

    tools = tool_discovery.build_tools(user.role)

    async def event_stream():
        logger.info("[DIAG] event_stream ENTER conv=%d user=%d", payload.conversation_id, user.id)
        full: list[str] = []
        thinking_parts: list[str] = []
        tool_events: list[dict] = []
        timeline: list[dict] = []
        _pending_events: list[dict] = []
        _event_round = 0
        try:
            _session_key = f"conv_{payload.conversation_id}"
            重置粘滞(_session_key)
            for _round in range(MAX_TOOL_ROUNDS):
                logger.info("[DIAG] event_stream tool_round %d/%d", _round + 1, MAX_TOOL_ROUNDS)
                logger.info("[DIAG] event_stream calling chat_with_degradation_chain")
                result = await chat_with_degradation_chain(
                    messages,
                    payload.profile_key or "deepseek-v4-flash",
                    tools,
                    conversation_id=payload.conversation_id,
                )
                logger.info("[DIAG] event_stream chat returned tool_calls=%s error=%s",
                    bool(result.get("tool_calls")), bool(result.get("error")))
                if result.get("error"):
                    error_msg = result.get("error") or ""
                    yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n".encode("utf-8")
                    break
                if result.get("thinking"):
                    thinking = str(result["thinking"])
                    thinking_parts.append(thinking)
                    timeline.append({"type": "thinking", "content": thinking})
                    logger.info("[DIAG] timeline APPEND thinking len=%d total=%d", len(thinking), len(timeline))
                    yield f"data: {json.dumps({'type': 'thinking', 'content': thinking}, ensure_ascii=False)}\n\n".encode("utf-8")
                tool_calls = result.get("tool_calls") or []
                if not tool_calls and result.get("finish_reason") == "tool_calls" and tools:
                    result = await recover_tool_calls(messages, payload.profile_key or "deepseek-v4-flash", tools)
                    tool_calls = result.get("tool_calls") or []
                # 兜底：检查 content 里是否有 XML 式工具调用标记
                if not tool_calls:
                    clean_content, inline_calls = parse_inline_tool_calls(result.get("content", ""))
                    if inline_calls:
                        result["content"] = clean_content
                        tool_calls = inline_calls
                        logger.info("[DIAG] event_stream parsed %d inline tool calls from chat() content", len(inline_calls))
                if not tool_calls:
                    logger.info("[DIAG] event_stream entering _yield_final_stream")
                    stream_kwargs: dict = {"messages": messages}
                    if payload.profile_key:
                        stream_kwargs["profile_key"] = payload.profile_key
                    inline_from_stream = None
                    async for chunk in _yield_final_stream(
                        stream_kwargs, full, thinking_parts, timeline,
                        profile_key=payload.profile_key or "deepseek-v4-flash",
                        conversation_id=payload.conversation_id,
                    ):
                        if isinstance(chunk, dict) and chunk.get("type") == "_inline_tool_calls":
                            inline_from_stream = chunk.get("tool_calls", [])
                        else:
                            yield chunk
                    if inline_from_stream:
                        tool_calls = inline_from_stream
                        logger.info("[DIAG] event_stream re-entering tool loop with %d inline tool calls from stream", len(tool_calls))
                    else:
                        logger.info("[DIAG] event_stream _yield_final_stream finished")
                        break
                logger.info("[DIAG] event_stream executing tool_calls count=%d", len(tool_calls))
                content_source = "".join(full) if full else (result.get("content") or "")
                messages.append({
                    "role": "assistant",
                    "content": content_source,
                    "tool_calls": _tool_calls_for_history(tool_calls),
                })
                _event_round_id = f"round_{_event_round}"
                _event_round += 1
                _pending_events.append({
                    "event_type": "assistant_msg", "payload": {"content": content_source},
                    "llm_response_id": _event_round_id,
                })
                for tc in tool_calls:
                    fn = tc.get("function", tc)
                    _pending_events.append({
                        "event_type": "tool_call",
                        "payload": {
                            "id": tc.get("id") or fn.get("id") or "",
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", {}),
                        },
                        "llm_response_id": _event_round_id,
                    })

                # ── Phase 1: parse + detect slow tools + yield all tool_call events ──
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
                        if inner_name in SLOW_SKILL_NAMES:
                            resolved_slow = inner_name
                    elif name in SLOW_SKILL_NAMES:
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
                    yield f"data: {_j(call_event)}\n\n".encode("utf-8")

                # ── Phase 2: slow tools → background queue ──────────────────
                from ..handlers.tasks import _submit_slow_tool_task
                has_slow = False
                for tool in parsed_tools:
                    if not tool["slow_name"]:
                        continue
                    has_slow = True
                    task_id = await _submit_slow_tool_task(
                        conversation_id=payload.conversation_id,
                        user_id=user.id,
                        tool_name=tool["slow_name"],
                        skill_args=tool["args"],
                        caller=f"user:{user.id}",
                        caller_role=user.role,
                    )
                    tool_result = {
                        "background": True,
                        "task_id": task_id,
                        "message": f"🛠️ 后台任务 [{tool['slow_name']}] 已提交，完成后将通过站内信通知你。",
                    }
                    result_event = {"type": "tool_result", "name": tool["name"], "result": tool_result}
                    tool_events.append(result_event)
                    timeline.append(result_event)
                    yield f"data: {_j(result_event)}\n\n".encode("utf-8")
                    tool_message = {
                        "role": "tool",
                        "name": tool["name"],
                        "content": _j(tool_result),
                    }
                    if tool["tool_call_id"]:
                        tool_message["tool_call_id"] = tool["tool_call_id"]
                    messages.append(tool_message)
                    _pending_events.append({
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
                        from app.database import AsyncSessionLocal as _ASL
                        async with _ASL() as _db:
                            _conv = await _db.get(AgentConversation, payload.conversation_id)
                            if _conv:
                                _conv.processing = True
                                await _db.commit()
                    except Exception as _pe:
                        logger.warning("Failed to mark processing flag: %s", _pe)

                # ── Phase 3: fast tools → concurrent execution ──────────────
                fast_tools = [t for t in parsed_tools if not t["slow_name"]]
                if fast_tools:
                    SEM_MAX = 5
                    sem = asyncio.Semaphore(SEM_MAX)
                    AGENT_CODE = "erp_chat"

                    async def _exec_one(tool: dict) -> dict:
                        async with sem:
                            try:
                                from app.database import AsyncSessionLocal as _ASL
                                async with _ASL() as _pol_db:
                                    pol = await check_action_allowed(
                                        _pol_db, tool["name"], AGENT_CODE,
                                        user.id, payload.conversation_id,
                                    )
                                if not pol.get("allowed"):
                                    pol_result = {
                                        "policy_action": pol["action"],
                                        "reason": pol.get("reason", ""),
                                        "approval_id": pol.get("approval_id"),
                                        "tool_name": pol.get("tool_name", tool["name"]),
                                    }
                                    return {"name": tool["name"], "tool_call_id": tool["tool_call_id"], "result": pol_result}
                                if tool["name"] == "skill_list":
                                    result = await tool_discovery.handle_skill_list(tool["args"], user.role)
                                elif tool["name"] == "skill_describe":
                                    result = await tool_discovery.handle_skill_describe(tool["args"], user.role)
                                elif tool["name"] == "skill_use":
                                    result = await tool_discovery.handle_skill_use(
                                        tool["args"], caller=f"user:{user.id}", caller_role=user.role,
                                    )
                                else:
                                    module_key, action = tool_discovery.parse_tool_name(tool["name"])
                                    result = await call_capability(
                                        module_key, action, tool["args"],
                                        caller=f"user:{user.id}", caller_role=user.role,
                                    )
                            except Exception as exc:
                                result = {"error": str(exc)}
                            return {"name": tool["name"], "tool_call_id": tool["tool_call_id"], "result": result}

                    tasks = [_exec_one(t) for t in fast_tools]
                    for coro in asyncio.as_completed(tasks):
                        outcome = await coro
                        result_data = outcome["result"]
                        if isinstance(result_data, dict) and result_data.get("policy_action") == "confirm":
                            result_data["approval_required"] = True
                        result_event = {"type": "tool_result", "name": outcome["name"], "result": result_data}
                        tool_events.append(result_event)
                        timeline.append(result_event)
                        yield f"data: {_j(result_event)}\n\n".encode("utf-8")
                        tool_message = {
                            "role": "tool",
                            "name": outcome["name"],
                            "content": _j(result_data),
                        }
                        if outcome["tool_call_id"]:
                            tool_message["tool_call_id"] = outcome["tool_call_id"]
                        messages.append(tool_message)
                        _pending_events.append({
                            "event_type": "tool_result",
                            "payload": {
                                "tool_call_id": outcome["tool_call_id"],
                                "name": outcome["name"],
                                "result": result_data,
                            },
                            "llm_response_id": None,
                        })

                # ── 粘滞检测 ────────────────
                _stuck_check = {"stuck": False}
                if tool_calls:
                    for tc in tool_calls:
                        fn = tc.get("function", tc)
                        _stuck_check = 检测粘滞(
                            tool_name=fn.get("name", ""),
                            tool_args=fn.get("arguments", {}),
                            error_text=None, is_empty_response=False,
                            session_key=_session_key,
                        )
                        if _stuck_check.get("stuck"):
                            break
                else:
                    has_error = bool(result.get("error"))
                    is_empty = not result.get("content") and not result.get("tool_calls")
                    _stuck_check = 检测粘滞(
                        tool_name=None, tool_args=None,
                        error_text=str(result.get("error"))[:100] if has_error else None,
                        is_empty_response=is_empty,
                        session_key=_session_key,
                    )
                if _stuck_check.get("stuck"):
                    logger.warning("粘滞检测打断工具循环: %s", _stuck_check["reason"])
                    yield f"data: {json.dumps({'type': 'error', 'content': _stuck_check['reason']}, ensure_ascii=False)}\n\n".encode("utf-8")
                    break
        except Exception as exc:
            logger.info("[DIAG] event_stream EXCEPTION %s: %s", type(exc).__name__, str(exc)[:300])
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)}, ensure_ascii=False)}\n\n".encode("utf-8")
        finally:
            try:
                from app.database import AsyncSessionLocal
                logger.info("[DIAG] event_stream starting DB persist")
                safe_tool_events = json.loads(json.dumps(tool_events, default=str))
                async with AsyncSessionLocal() as s2:
                    if full:
                        clean_assistant_content = final_clean_content("".join(full))
                        msg = await conv_svc.add_message(s2, user.id, payload.conversation_id, "assistant", clean_assistant_content)
                        await conv_svc.add_message_meta(
                            s2, owner_id=user.id,
                            conversation_id=payload.conversation_id,
                            message_id=msg.id,
                            thinking="\n".join(thinking_parts),
                            references=_references_from_tool_events(tool_events),
                            tool_events=safe_tool_events,
                            timeline=timeline,
                        )
                        logger.info("[DIAG] persist DONE msg=%d timeline_len=%d full_len=%d", msg.id, len(timeline), len(full))
                        user_msg_count = await conv_svc.count_conversation_messages(s2, user.id, payload.conversation_id)
                        if user_msg_count > 0 and user_msg_count % EVOLVE_EVERY_N_MESSAGES == 0:
                            logger.info("[DIAG] event_stream submitting profile_evolve task (fire-and-forget)")
                            asyncio.create_task(_submit_profile_evolve_task(payload.conversation_id, user.id))
                            logger.info("[DIAG] event_stream profile_evolve task submitted")
                        try:
                            from app.models.system import SystemTaskQueue
                            task = SystemTaskQueue(
                                task_type="memory_distill",
                                parameters=json.dumps({
                                    "conversation_id": payload.conversation_id,
                                    "owner_id": user.id,
                                    "user_content": payload.content,
                                    "assistant_content": clean_assistant_content,
                                }),
                                status="pending", priority=0, module="agent",
                                creator_id=user.id,
                            )
                            s2.add(task)
                            await s2.commit()
                        except Exception as e:
                            logger.warning("Memory distill enqueue failed (non-fatal): %s", e)
                if full and not any(
                    e["event_type"] == "assistant_msg" and e["payload"].get("content", "") == clean_assistant_content[:200]
                    for e in _pending_events
                ):
                    _final_rid = f"round_{_event_round}"
                    _event_round += 1
                    _pending_events.append({
                        "event_type": "assistant_msg",
                        "payload": {"content": clean_assistant_content},
                        "llm_response_id": _final_rid,
                    })
                for pe in _pending_events:
                    try:
                        await record_event(
                            s2, payload.conversation_id,
                            pe["event_type"], pe["payload"],
                            pe.get("llm_response_id"),
                        )
                    except Exception as pe_exc:
                        logger.warning("record_event failed (non-fatal): %s", pe_exc)
                logger.info("[DIAG] event_stream DB persist done (events=%d)", len(_pending_events))
            except Exception as exc:
                logger.warning("event_stream persist/evolve failed (non-fatal): %s", exc)
            logger.info("[DIAG] event_stream yielding [DONE]")
            yield b"data: [DONE]\n\n"
            logger.info("[DIAG] event_stream EXIT")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _submit_profile_evolve_task(conversation_id: int, owner_id: int) -> None:
    """Submit background profile evolution task to SystemTaskQueue."""
    try:
        from datetime import datetime, timezone, timedelta
        from app.database import AsyncSessionLocal
        from app.models.system import SystemTaskQueue
        from ..init_db import ensure_user_profile

        async with AsyncSessionLocal() as db:
            profile = await ensure_user_profile(db, owner_id)
            if profile.evolved_at:
                if datetime.now(timezone.utc) - profile.evolved_at < timedelta(minutes=30):
                    return
            task = SystemTaskQueue(
                task_type="profile_evolve",
                parameters=json.dumps({"conversation_id": conversation_id, "owner_id": owner_id}),
                status="pending", priority=0, module="agent", creator_id=owner_id,
            )
            db.add(task)
            await db.commit()
    except Exception as exc:
        logger.warning("_submit_profile_evolve_task failed (non-fatal): %s", exc)
