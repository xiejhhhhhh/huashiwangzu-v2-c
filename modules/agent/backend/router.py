import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("v2.agent.router")

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.gateway.router import gateway_router
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import call_capability, register_capability
from app.services.task_worker import register_task_handler

MODULE_BACKEND_DIR = Path(__file__).resolve().parent
if str(MODULE_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_BACKEND_DIR))

from action_policy import check_action_allowed, resolve_approval, list_pending_approvals
import conversation_service as conv_svc
from init_db import ensure_default_prompts, ensure_timeline_column, ensure_user_profile, update_existing_prompts, ensure_event_table, ensure_processing_column
from model_client import recover_tool_calls, parse_inline_tool_calls, final_clean_content
import tool_discovery
from profile_evolve import handle_profile_evolve
ENGINE_DIR = (MODULE_BACKEND_DIR / ".." / "engine").resolve()
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))
import 事件存储
from 事件存储 import record_event
import 引擎
from 引擎 import 装配上下文, chat_with_degradation_chain, chat_stream_with_degradation_chain
from 粘滞检测 import 检测粘滞, 重置 as 重置粘滞

# 注册后台任务处理器（框架 worker 自动消费）
register_task_handler("profile_evolve", handle_profile_evolve)


async def _handle_memory_dream(params: dict) -> dict:
    """Handle memory_dream task from queue. Calls dream on memory module."""
    owner_id = params.get("owner_id")
    if not owner_id:
        return {"error": "Missing owner_id"}
    try:
        from 分层记忆 import 触发dream
        await 触发dream(owner_id)
        return {"status": "ok", "owner_id": owner_id}
    except Exception as e:
        logger.warning("Memory dream handler failed (non-fatal): %s", e)
        return {"error": str(e)}


register_task_handler("memory_dream", _handle_memory_dream)


async def _handle_memory_distill(params: dict) -> dict:
    """Handle memory_distill task from queue."""
    conversation_id = params.get("conversation_id")
    owner_id = params.get("owner_id")
    user_content = params.get("user_content", "")
    assistant_content = params.get("assistant_content", "")
    if not conversation_id or not owner_id:
        return {"error": "Missing required params"}
    try:
        await _submit_memory_distill_task(conversation_id, owner_id, user_content, assistant_content)
        return {"status": "ok"}
    except Exception as e:
        logger.warning("Memory distill handler failed: %s", e)
        return {"error": str(e)}


register_task_handler("memory_distill", _handle_memory_distill)

router = APIRouter(prefix="/api/agent", tags=["agent"])

MAX_TOOL_ROUNDS = 5
EVOLVE_EVERY_N_MESSAGES = 3  # 每 N 轮用户消息触发一次画像进化

# 需后台执行的慢能力集合（不在 SSE 流中同步 await，改为入队后台执行）
SLOW_SKILL_NAMES: set[str] = {
    "image-gen__generate",
    "office-gen__convert",
}


def _j(obj) -> str:
    """json.dumps with datetime fallback."""
    return json.dumps(obj, ensure_ascii=False, default=str)


class CreateConvRequest(BaseModel):
    title: str = "新对话"


class RenameConvRequest(BaseModel):
    title: str


class ChatRequest(BaseModel):
    conversation_id: int
    content: str
    profile_key: str | None = None


class UpdatePromptRequest(BaseModel):
    content: str


def _conversation_payload(item) -> dict:
    return {"id": item.id, "title": item.title, "status": item.status}


def _references_from_tool_events(events: list[dict]) -> list[dict]:
    refs: list[dict] = []
    for event in events:
        if event.get("type") != "tool_result":
            continue
        name = event.get("name", "tool") or ""
        result = event.get("result", {}) or {}
        # 知识库检索结果（通过 skill_use 调用或直接调用）：提取文件名和页码
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


async def _yield_final_stream(kwargs: dict, full: list[str], thinking_parts: list[str], timeline: list[dict], profile_key: str = "deepseek-v4-flash", conversation_id: int | None = None):
    """Stream final content while checking for inline XML tool calls.

    Buffers token events, checks accumulated content for inline tool calls when
    streaming completes. If inline calls found, they are stripped from `full`
    and a special dict event `{"type": "_inline_tool_calls", "tool_calls": [...]}`
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

    # After stream completion, check accumulated content for inline tool calls
    full_content = "".join(full)
    clean_content, inline_calls = parse_inline_tool_calls(full_content)
    if inline_calls:
        # Inline tool calls found — strip markup, don't flush tokens to frontend
        full.clear()
        full.append(clean_content)
        logger.info("[DIAG] _yield_final_stream found %d inline tool calls, re-entering tool loop", len(inline_calls))
        # Yield a special sentinel that main loop interprets as "re-enter tool loop"
        yield {"type": "_inline_tool_calls", "tool_calls": inline_calls}
        return

    # No inline calls — flush buffered tokens to frontend
    for etype, econtent in token_buffer:
        yield f"data: {json.dumps({'type': 'token', 'content': econtent}, ensure_ascii=False)}\n\n".encode("utf-8")

    logger.info("[DIAG] _yield_final_stream EXIT after %d events — no inline calls", event_count)


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "agent", "status": "ok"})


@router.get("/profiles")
async def list_profiles(user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=gateway_router.list_profiles())


@router.get("/tools")
async def list_tools(user: User = Depends(require_permission("viewer"))):
    tools = tool_discovery.build_tools(user.role)
    return ApiResponse(data=tools)


# ── 三层提示词管理接口（仅管理员） ─────────────────────────

@router.get("/system-prompt")
async def get_system_prompt(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    """获取当前系统提示词内容（只读，所有人可看）。"""
    content = await conv_svc.get_system_prompt(db)
    return ApiResponse(data={"content": content})


@router.put("/system-prompt")
async def update_system_prompt(
    payload: UpdatePromptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    """管理员更新系统提示词。"""
    prompt = await conv_svc.update_system_prompt(db, payload.content, user.id)
    return ApiResponse(data={"id": prompt.id, "content": prompt.content, "version": prompt.version})


@router.get("/enterprise-prompt")
async def get_enterprise_prompt(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    """获取当前企业提示词内容。"""
    content = await conv_svc.get_enterprise_prompt(db)
    return ApiResponse(data={"content": content})


@router.put("/enterprise-prompt")
async def update_enterprise_prompt(
    payload: UpdatePromptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    """管理员更新企业提示词。"""
    prompt = await conv_svc.update_enterprise_prompt(db, payload.content, user.id)
    return ApiResponse(data={"id": prompt.id, "content": prompt.content, "version": prompt.version})


@router.get("/user-profile")
async def get_my_profile(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    """获取当前用户的个人画像。"""
    from init_db import ensure_user_profile
    profile = await ensure_user_profile(db, user.id)
    return ApiResponse(data={
        "owner_id": profile.owner_id,
        "profile_data": json.loads(profile.profile_data) if profile.profile_data else {},
        "version": profile.version,
        "evolved_at": profile.evolved_at.isoformat() if profile.evolved_at else None,
        "conversation_count": profile.conversation_count,
    })


# ── 对话接口 ───────────────────────────────────────────────

@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    items = await conv_svc.list_conversations(db, user.id)
    return ApiResponse(data=[_conversation_payload(item) for item in items])


@router.post("/conversations")
async def create_conversation(payload: CreateConvRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    await ensure_processing_column(db)
    await ensure_event_table(db)
    item = await conv_svc.create_conversation(db, user.id, payload.title)
    return ApiResponse(data=_conversation_payload(item))


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: int,
    payload: RenameConvRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    item = await conv_svc.rename_conversation(db, user.id, conversation_id, payload.title)
    return ApiResponse(data=_conversation_payload(item) if item else None)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data={"deleted": await conv_svc.delete_conversation(db, user.id, conversation_id)})


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=await conv_svc.get_messages_with_meta(db, user.id, conversation_id))


# ── 聊天 + 画像进化（3-layer） ─────────────────────────────

@router.post("/chat")
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
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
    agent_code = "erp_chat"  # 主对话 agent 的配置标识
    messages, engine_diag = await 装配上下文(
        db, payload.conversation_id, payload.content,
        profile_key, user.id, agent_code=agent_code,
    )

    # 记录装配诊断事件（批5：用于重放展示装配细节）
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

    # ── 记忆召回：自动检索用户相关记忆，注入 system prompt ──────────
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
                    # 注入到已有的 system message 中
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
                    async for chunk in _yield_final_stream(stream_kwargs, full, thinking_parts, timeline, profile_key=payload.profile_key or "deepseek-v4-flash", conversation_id=payload.conversation_id):
                        if isinstance(chunk, dict) and chunk.get("type") == "_inline_tool_calls":
                            inline_from_stream = chunk.get("tool_calls", [])
                        else:
                            yield chunk
                    if inline_from_stream:
                        tool_calls = inline_from_stream
                        logger.info("[DIAG] event_stream re-entering tool loop with %d inline tool calls from stream", len(tool_calls))
                        # Continue to tool execution below instead of breaking
                    else:
                        logger.info("[DIAG] event_stream _yield_final_stream finished")
                        break
                logger.info("[DIAG] event_stream executing tool_calls count=%d", len(tool_calls))
                # 若 inline 工具调用来自流式，内容在 full 中而非 result["content"]
                content_source = "".join(full) if full else (result.get("content") or "")
                messages.append({
                    "role": "assistant",
                    "content": content_source,
                    "tool_calls": _tool_calls_for_history(tool_calls),
                })
                # 记录引擎事件
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
                    # 标记对话有后台任务（多 worker 守护）
                    from models import AgentConversation
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
                                # ── Sensitive action policy check ──────────
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
                                    return {
                                        "name": tool["name"],
                                        "tool_call_id": tool["tool_call_id"],
                                        "result": pol_result,
                                    }

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
                            return {
                                "name": tool["name"],
                                "tool_call_id": tool["tool_call_id"],
                                "result": result,
                            }

                    tasks = [_exec_one(t) for t in fast_tools]
                    for coro in asyncio.as_completed(tasks):
                        outcome = await coro
                        # Mark approval-required results for frontend
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

                # ── 批4：粘滞检测 —— 每轮工具执行完后检查 ────────────────
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
            # ── 持久化 + 画像进化：用独立 try/except 兜住，失败只记日志，绝不阻断 [DONE] ──
            try:
                from app.database import AsyncSessionLocal
                logger.info("[DIAG] event_stream starting DB persist")
                # tool_events 可能含 datetime 等非 JSON 对象 → 安全序列化一把
                safe_tool_events = json.loads(json.dumps(tool_events, default=str))
                async with AsyncSessionLocal() as s2:
                    if full:
                        clean_assistant_content = final_clean_content("".join(full))
                        msg = await conv_svc.add_message(s2, user.id, payload.conversation_id, "assistant", clean_assistant_content)
                        await conv_svc.add_message_meta(
                            s2,
                            owner_id=user.id,
                            conversation_id=payload.conversation_id,
                            message_id=msg.id,
                            thinking="\n".join(thinking_parts),
                            references=_references_from_tool_events(tool_events),
                            tool_events=safe_tool_events,
                            timeline=timeline,
                        )
                        logger.info("[DIAG] persist DONE msg=%d timeline_len=%d full_len=%d", msg.id, len(timeline), len(full))
                        # 画像进化：fire-and-forget，不阻塞流收尾
                        user_msg_count = await conv_svc.count_conversation_messages(s2, user.id, payload.conversation_id)
                        if user_msg_count > 0 and user_msg_count % EVOLVE_EVERY_N_MESSAGES == 0:
                            logger.info("[DIAG] event_stream submitting profile_evolve task (fire-and-forget)")
                            asyncio.create_task(_submit_profile_evolve_task(payload.conversation_id, user.id))
                            logger.info("[DIAG] event_stream profile_evolve task submitted")
                        # 记忆蒸馏：每轮对话后异步提取关键事实并落库（经 SystemTaskQueue）
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
                                status="pending",
                                priority=0,
                                module="agent",
                                creator_id=user.id,
                            )
                            s2.add(task)
                            await s2.commit()
                        except Exception as e:
                            logger.warning("Memory distill enqueue failed (non-fatal): %s", e)
                # 记录引擎事件：如果 streaming 阶段产生了全量内容且未被 tool 循环记录，在此记录
                if full and not any(e["event_type"] == "assistant_msg" and e["payload"].get("content", "") == clean_assistant_content[:200] for e in _pending_events):
                    _final_rid = f"round_{_event_round}"
                    _event_round += 1
                    _pending_events.append({
                        "event_type": "assistant_msg",
                        "payload": {"content": clean_assistant_content},
                        "llm_response_id": _final_rid,
                    })
                # 统一持久化所有待处理引擎事件
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
            # ★ 无论正常结束/异常/持久化失败，永远发 [DONE]
            logger.info("[DIAG] event_stream yielding [DONE]")
            yield b"data: [DONE]\n\n"
            logger.info("[DIAG] event_stream EXIT")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 跨模块能力注册：Agent 提示词读写 ─────────────────────────
# Agent 通过 tool_discovery.build_tools(role) 自动发现这些能力；
# register_capability 的 min_role 确保低权限用户的 Agent 看不到高权限工具，
# 且 call_capability 执行侧二次拦截，双重防护。


async def _submit_slow_tool_task(
    conversation_id: int, user_id: int, tool_name: str,
    skill_args: dict, caller: str, caller_role: str,
) -> int:
    """将慢工具提交到 SystemTaskQueue 后台执行。

    Returns: task_id
    """
    from datetime import datetime, timezone
    from app.database import AsyncSessionLocal
    from app.models.system import SystemTaskQueue

    task_params = {
        "conversation_id": conversation_id,
        "owner_id": user_id,
        "tool_name": tool_name,
        "skill_args": skill_args,
        "caller": caller,
        "caller_role": caller_role,
    }
    async with AsyncSessionLocal() as db:
        task = SystemTaskQueue(
            task_type="agent_execute_slow_tool",
            parameters=json.dumps(task_params, ensure_ascii=False),
            status="pending",
            priority=0,
            module="agent",
            creator_id=user_id,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task.id


async def _handle_slow_tool(params: dict) -> dict:
    """后台任务处理器：执行慢工具，结果写入对话，发 IM 通知。

    框架 task_worker 消费。逐任务独立 DB 会话 + commit。
    成功：结果作为 assistant 消息写入对话 + im.notify 推送。
    失败：错误消息写入对话 + im.notify 推送失败信息。
    """
    conversation_id = params.get("conversation_id")
    owner_id = params.get("owner_id")
    tool_name = params.get("tool_name", "")
    skill_args = params.get("skill_args", {})
    caller = params.get("caller", "")
    caller_role = params.get("caller_role", "viewer")

    if not conversation_id or not owner_id or not tool_name:
        return {"error": "Missing required params"}

    logger.info("Slow tool background exec: tool=%s conv=%s user=%s", tool_name, conversation_id, owner_id)

    try:
        # 执行慢工具
        if tool_name.startswith("skill_use__"):
            # skill_use 透传格式：实际走 skill_use 的 action 名的参数
            inner_name = skill_args.get("name", "")
            inner_args = skill_args.get("args", {})
            if isinstance(inner_args, str):
                import json as _j2
                try:
                    inner_args = _j2.loads(inner_args) if inner_args.strip() else {}
                except Exception:
                    inner_args = {}
            if not isinstance(inner_args, dict):
                inner_args = {}
            tool_result = await call_capability(
                *tool_discovery.parse_tool_name(inner_name),
                inner_args, caller=caller, caller_role=caller_role,
            )
        else:
            tool_result = await call_capability(
                *tool_discovery.parse_tool_name(tool_name),
                skill_args, caller=caller, caller_role=caller_role,
            )
    except Exception as exc:
        tool_result = {"error": str(exc)}

    # 写结果到对话
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            import conversation_service as conv_svc2
            result_text = json.dumps(tool_result, ensure_ascii=False, default=str)
            if isinstance(tool_result, dict) and tool_result.get("error"):
                await conv_svc2.add_message(
                    db, owner_id, conversation_id, "assistant",
                    f"⚠️ 后台任务 [{tool_name}] 执行失败：{tool_result['error']}",
                )
            else:
                await conv_svc2.add_message(
                    db, owner_id, conversation_id, "assistant",
                    f"✅ 后台任务 [{tool_name}] 已完成。结果：\n{result_text[:2000]}",
                )

            # 发 IM 通知
            try:
                # 用 call_capability 调 im.notify
                notify_result = await call_capability(
                    "im", "notify",
                    {
                        "user_id": owner_id,
                        "content": f"✅ 你的后台任务 [{tool_name}] 已完成，请到 AI 助手对话中查看结果。",
                        "title": "后台任务完成",
                    },
                    caller=f"system:agent_worker",
                    caller_role="admin",
                )
                logger.info("Slow tool notify result: %s", notify_result)
            except Exception as notify_exc:
                logger.warning("Slow tool IM notify failed (non-fatal): %s", notify_exc)

            # 清除 conversation processing 标记
            try:
                from models import AgentConversation
                from sqlalchemy import select
                r = await db.execute(
                    select(AgentConversation).where(AgentConversation.id == conversation_id)
                )
                conv = r.scalar_one_or_none()
                if conv:
                    conv.processing = False
                    await db.commit()
            except Exception as clear_exc:
                logger.warning("Failed to clear processing flag: %s", clear_exc)

            return {"status": "ok", "conversation_id": conversation_id}
        except Exception as persist_exc:
            logger.error("Failed to persist slow tool result: %s", persist_exc)
            return {"error": str(persist_exc)}


register_task_handler("agent_execute_slow_tool", _handle_slow_tool)


def _resolve_user_id(caller: str) -> int:
    """caller: user:{id} → int user_id。"""
    from app.core.exceptions import PermissionDenied

    try:
        prefix, raw_id = caller.split(":", 1)
        if prefix == "user":
            return int(raw_id)
    except (TypeError, ValueError):
        pass
    raise PermissionDenied("Invalid caller")


async def _cap_get_system_prompt(params: dict, caller: str) -> dict:
    """读取系统提示词（仅 admin）。"""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        content = await conv_svc.get_system_prompt(db)
        return {"content": content}


async def _cap_update_system_prompt(params: dict, caller: str) -> dict:
    """更新系统提示词（仅 admin）。"""
    from app.database import AsyncSessionLocal

    content = params.get("content", "")
    if not content:
        return {"error": "content is required"}
    async with AsyncSessionLocal() as db:
        caller_uid = _resolve_user_id(caller)
        prompt = await conv_svc.update_system_prompt(db, content, caller_uid)
        return {"id": prompt.id, "content": prompt.content, "version": prompt.version}


async def _cap_get_enterprise_prompt(params: dict, caller: str) -> dict:
    """读取企业提示词（仅 admin）。"""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        content = await conv_svc.get_enterprise_prompt(db)
        return {"content": content}


async def _cap_update_enterprise_prompt(params: dict, caller: str) -> dict:
    """更新企业提示词（仅 admin）。"""
    from app.database import AsyncSessionLocal

    content = params.get("content", "")
    if not content:
        return {"error": "content is required"}
    async with AsyncSessionLocal() as db:
        caller_uid = _resolve_user_id(caller)
        prompt = await conv_svc.update_enterprise_prompt(db, content, caller_uid)
        return {"id": prompt.id, "content": prompt.content, "version": prompt.version}


async def _cap_get_my_profile(params: dict, caller: str) -> dict:
    """读取自己的个人画像。"""
    from app.database import AsyncSessionLocal

    owner_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        from init_db import ensure_user_profile

        profile = await ensure_user_profile(db, owner_id)
        return {
            "owner_id": profile.owner_id,
            "profile_data": json.loads(profile.profile_data) if profile.profile_data else {},
            "version": profile.version,
            "evolved_at": profile.evolved_at.isoformat() if profile.evolved_at else None,
            "conversation_count": profile.conversation_count,
        }


async def _cap_update_my_profile(params: dict, caller: str) -> dict:
    """更新自己的个人画像（仅能改自己的，owner 从 caller 解析）。"""
    from app.database import AsyncSessionLocal

    profile_data = params.get("profile_data")
    if not profile_data or not isinstance(profile_data, dict):
        return {"error": "profile_data (dict) is required"}
    owner_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        profile = await conv_svc.update_user_profile(db, owner_id, profile_data)
        return {
            "owner_id": profile.owner_id,
            "profile_data": json.loads(profile.profile_data) if profile.profile_data else {},
            "version": profile.version,
        }


# 注册能力（按权限矩阵，模块启动时自动执行）
register_capability(
    "agent", "get_system_prompt", _cap_get_system_prompt,
    description="读取当前系统提示词（管理员权限）。系统提示词定义了 Agent 的核心行为、知识库使用规则和联网能力规则。",
    brief="读取系统提示词",
    parameters={},
    min_role="admin",
)
register_capability(
    "agent", "update_system_prompt", _cap_update_system_prompt,
    description="更新系统提示词（管理员权限）。当管理员用户要求修改 Agent 底层行为规则时调用此工具。",
    brief="更新系统提示词",
    parameters={
        "content": {"type": "string", "description": "新的系统提示词内容"},
    },
    min_role="admin",
)
register_capability(
    "agent", "get_enterprise_prompt", _cap_get_enterprise_prompt,
    description="读取当前企业提示词（管理员权限）。企业提示词包含了公司背景、业务规则等企业上下文信息。",
    brief="读取企业提示词",
    parameters={},
    min_role="admin",
)
register_capability(
    "agent", "update_enterprise_prompt", _cap_update_enterprise_prompt,
    description="更新企业提示词（管理员权限）。当管理员用户要求修改公司/企业背景设定时调用此工具。",
    brief="更新企业提示词",
    parameters={
        "content": {"type": "string", "description": "新的企业提示词内容"},
    },
    min_role="admin",
)
register_capability(
    "agent", "get_my_profile", _cap_get_my_profile,
    description="读取当前用户的个人画像。个人画像包含用户的语气偏好、禁忌话题、关注领域和习惯，是系统自动学习的个性化配置。",
    brief="读取我的画像",
    parameters={},
    min_role="viewer",
)
register_capability(
    "agent", "update_my_profile", _cap_update_my_profile,
    description="更新当前用户的个人画像（仅能改自己的）。当用户要求修改自己的语气偏好、设定或个性化配置时调用此工具。owner 固定为当前用户，不允许修改他人画像。",
    brief="更新我的画像",
    parameters={
        "profile_data": {
            "type": "object",
            "description": "画像数据字典，包含 tone（语气偏好，字符串）、taboos（禁忌话题，字符串数组）、focus（关注领域，字符串数组）、habits（习惯描述，字符串数组）",
            "properties": {
                "tone": {"type": "string", "description": "语气偏好，如'简洁'、'专业'、'友好'"},
                "taboos": {"type": "array", "items": {"type": "string"}, "description": "禁忌话题列表"},
                "focus": {"type": "array", "items": {"type": "string"}, "description": "关注领域列表"},
                "habits": {"type": "array", "items": {"type": "string"}, "description": "习惯描述列表"},
            },
        },
    },
    min_role="viewer",
)

SUBAGENT_MAX_ROUNDS = 4
SUBAGENT_CONTEXT_LIMIT = 10


async def _cap_spawn_subagent(params: dict, caller: str) -> dict:
    """子 Agent：把子任务委托给一个独立工具循环，拿回结论。

    参数：
    - task: 任务描述（必填）
    - tools: 限定技能列表（可选，如 ["image-gen__generate", "web-tools__search"]）
    - context: 额外上下文（可选字符串，如参考信息）

    内部机制：起一个独立对话，跑工具循环直到出结论或到轮数上限。
    受 min_role / caller_role 约束，不能越权。
    """
    task = params.get("task", "")
    if not task or not isinstance(task, str):
        return {"error": "task is required"}

    # 权限：call_capability 已鉴权（agent.spawn_subagent 注册的 min_role 已拦），
    # 子 Agent 内部再调 call_capability 仍会二次鉴权，这里用 viewer 开工具可见性足矣
    caller_role = "viewer"
    extra_tools = params.get("tools") or []
    extra_context = params.get("context") or ""

    try:
        # 构建子 Agent 的系统提示词
        system_prompt = (
            "你是一个子 Agent，专注于完成一项具体任务，然后返回结论。\n\n"
            f"任务：{task}\n\n"
        )
        if extra_context:
            system_prompt += f"参考上下文：\n{extra_context}\n\n"
        system_prompt += (
            "规则：\n"
            "1. 使用可用工具完成任务，不要闲聊。\n"
            f"2. 最多 {SUBAGENT_MAX_ROUNDS} 轮工具调用，超限则返回已有结论。\n"
            "3. 完成目标后，清晰总结结论。\n"
            "4. 如果工具调用失败，尝试替代方案。\n"
            "5. 用中文回答。"
        )

        # 获取工具定义
        tools = tool_discovery.build_tools(caller_role)
        if extra_tools:
            # 过滤：只保留 task 中指定的技能相关工具，但始终保留 skill_list/describe/use
            allowed = set(extra_tools) | {"skill_list", "skill_describe", "skill_use"}
            tools = [t for t in tools if t.get("function", {}).get("name", "") in allowed]

        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # 子 Agent 工具循环
        full_content = ""
        for _round in range(SUBAGENT_MAX_ROUNDS):
            kwargs = {"messages": messages, "tools": tools}
            result = await gateway_router.chat(**kwargs)

            if result.get("error"):
                full_content = f"子 Agent 执行出错：{result['error']}"
                break

            content = result.get("content", "")
            tool_calls = result.get("tool_calls") or []

            # 兜底：检查 content 里的内联工具调用
            if not tool_calls:
                clean_content, inline_calls = parse_inline_tool_calls(content)
                if inline_calls:
                    result["content"] = clean_content
                    tool_calls = inline_calls

            if not tool_calls:
                # 没有工具调用 → 这是最终结论
                full_content = content
                break

            # 有工具调用：记录 assistant 消息，执行工具
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": _tool_calls_for_history(tool_calls),
            })

            for tc in tool_calls:
                fn = tc.get("function", tc)
                name = fn.get("name", "")
                try:
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        args = json.loads(args)
                except Exception:
                    args = {}

                if name == "skill_list":
                    tool_result = await tool_discovery.handle_skill_list(args, caller_role)
                elif name == "skill_describe":
                    tool_result = await tool_discovery.handle_skill_describe(args, caller_role)
                elif name == "skill_use":
                    tool_result = await tool_discovery.handle_skill_use(
                        args, caller=caller, caller_role=caller_role,
                    )
                else:
                    module_key, action = tool_discovery.parse_tool_name(name)
                    tool_result = await call_capability(
                        module_key, action, args,
                        caller=caller, caller_role=caller_role,
                    )

                messages.append({
                    "role": "tool",
                    "name": name,
                    "content": _j(tool_result),
                    "tool_call_id": tc.get("id", ""),
                })

        # 执行完所有轮次仍无结论，用最后一条 assistant 内容
        if not full_content:
            # 取最后一条 assistant 消息
            for msg in reversed(messages):
                if msg["role"] == "assistant":
                    full_content = msg.get("content", "") or ""
                    break

        # 清理内容中的工具标记
        from model_client import final_clean_content
        full_content = final_clean_content(full_content)

        return {
            "success": True,
            "data": {
                "conclusion": full_content or "子 Agent 未生成结论",
                "rounds_used": _round + 1,
                "messages_count": len(messages),
            },
        }
    except Exception as exc:
        return {"error": f"子 Agent 执行异常：{exc}"}


register_capability(
    "agent", "spawn_subagent", _cap_spawn_subagent,
    description="把子任务委托给一个独立子 Agent 执行并拿回结论。子 Agent 会用自己的工具循环执行任务，完成后返回结论。适用于拆解复杂任务（如同时查资料、生图、整理文档）。",
    brief="委托子Agent执行任务",
    parameters={
        "task": {"type": "string", "description": "任务描述，说明子Agent需要完成什么"},
        "tools": {
            "type": "array",
            "items": {"type": "string"},
            "description": "限定可用技能列表（可选），如 ['web-tools__search', 'image-gen__generate']",
        },
        "context": {"type": "string", "description": "额外上下文（可选），如已有信息或参考数据"},
    },
    min_role="viewer",
)


# ── 引擎批5：Admin 只读接口（重放 + 概览） ────────────────────────────


@router.get("/admin/replay/{conversation_id}")
async def admin_replay(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    """事件重放：读取 agent_events，按轮次重建上下文装配过程。
    
    返回每轮的：用户输入、装配诊断、回复、工具调用/结果、压缩、降级。
    纯读，不改事件。
    """
    events = await 事件存储.read_events(db, conversation_id)
    if not events:
        return ApiResponse(data={"conversation_id": conversation_id, "rounds": [], "total_events": 0})

    rounds: list[dict] = []
    current_round: dict | None = None

    for ev in events:
        ev_dict = {
            "id": ev.id,
            "event_type": ev.event_type,
            "payload": ev.payload,
            "llm_response_id": ev.llm_response_id,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        }
        etype = ev.event_type

        if etype == "user_msg":
            if current_round:
                rounds.append(current_round)
            current_round = {
                "round_start_id": ev.id,
                "user_input": ev.payload.get("content", ""),
                "assembly_diag": None,
                "assistant_msg": None,
                "tool_calls": [],
                "tool_results": [],
                "compaction": None,
                "degradation": None,
                "events": [ev_dict],
            }
        elif etype == "assembly_diag" and current_round:
            current_round["assembly_diag"] = ev.payload
            current_round["events"].append(ev_dict)
        elif etype == "assistant_msg" and current_round:
            current_round["assistant_msg"] = ev.payload.get("content", "")
            current_round["events"].append(ev_dict)
        elif etype == "tool_call" and current_round:
            current_round["tool_calls"].append({
                "id": ev.payload.get("id", ""),
                "name": ev.payload.get("name", ""),
                "arguments": ev.payload.get("arguments", {}),
            })
            current_round["events"].append(ev_dict)
        elif etype == "tool_result" and current_round:
            current_round["tool_results"].append({
                "tool_call_id": ev.payload.get("tool_call_id", ""),
                "name": ev.payload.get("name", ""),
                "result": ev.payload.get("result", {}),
            })
            current_round["events"].append(ev_dict)
        elif etype == "compaction":
            # 压缩事件归到最近的 round 或独立
            if current_round:
                current_round["compaction"] = {
                    "folded_count": ev.payload.get("folded_count", 0),
                    "summary_preview": ev.payload.get("summary", "")[:300],
                    "compression_ratio": ev.payload.get("compression_ratio"),
                }
                current_round["events"].append(ev_dict)
            else:
                rounds.append({
                    "round_start_id": ev.id,
                    "user_input": "",
                    "assembly_diag": None,
                    "assistant_msg": None,
                    "tool_calls": [],
                    "tool_results": [],
                    "compaction": {
                        "folded_count": ev.payload.get("folded_count", 0),
                        "summary_preview": ev.payload.get("summary", "")[:300],
                        "compression_ratio": ev.payload.get("compression_ratio"),
                    },
                    "degradation": None,
                    "events": [ev_dict],
                })
                current_round = None
        elif etype == "degradation" and current_round:
            current_round["degradation"] = {
                "from_profile": ev.payload.get("from", ""),
                "to_profile": ev.payload.get("to", ""),
                "reason": ev.payload.get("reason", ""),
            }
            current_round["events"].append(ev_dict)
        else:
            if current_round:
                current_round["events"].append(ev_dict)

    if current_round:
        rounds.append(current_round)

    return ApiResponse(data={
        "conversation_id": conversation_id,
        "rounds": rounds,
        "total_events": len(events),
    })


@router.get("/admin/overview")
async def admin_overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    """引擎概览：记忆/经验/预算/压缩/降级/粘滞 各模块聚合统计。
    
    所有数字真实来自 DB，非写死假数。
    """
    from sqlalchemy import text, func as sa_func

    result: dict = {}

    # 1. 记忆概览（agent_memory 表，跨所有用户）
    try:
        mem_count = await db.scalar(text("SELECT COUNT(*) FROM agent_memory"))
        mem_with_embedding = await db.scalar(text("SELECT COUNT(*) FROM agent_memory WHERE embedding IS NOT NULL"))
        mem_avg_confidence = await db.scalar(text("SELECT COALESCE(AVG(confidence), 0) FROM agent_memory"))
        mem_avg_recency = await db.scalar(text("SELECT COALESCE(AVG(recency_score), 0) FROM agent_memory"))
        mem_link_count = await db.scalar(text("SELECT COUNT(*) FROM memory_links"))
        mem_owner_count = await db.scalar(text("SELECT COUNT(DISTINCT owner_id) FROM agent_memory"))
        result["memory"] = {
            "total_count": mem_count or 0,
            "with_embedding": mem_with_embedding or 0,
            "avg_confidence": round(float(mem_avg_confidence or 0), 3),
            "avg_recency_score": round(float(mem_avg_recency or 0), 3),
            "link_count": mem_link_count or 0,
            "owner_count": mem_owner_count or 0,
        }
    except Exception as e:
        logger.warning("Admin overview memory query failed: %s", e)
        result["memory"] = {"error": str(e)}

    # 2. 经验概览（agent_experiences）
    try:
        exp_count = await db.scalar(text("SELECT COUNT(*) FROM agent_experiences"))
        exp_active = await db.scalar(text("SELECT COUNT(*) FROM agent_experiences WHERE active = true"))
        exp_inactive = await db.scalar(text("SELECT COUNT(*) FROM agent_experiences WHERE active = false"))
        exp_avg_weight = await db.scalar(text("SELECT COALESCE(AVG(success_weight), 0) FROM agent_experiences WHERE active = true"))
        exp_total_fails = await db.scalar(text("SELECT COALESCE(SUM(fail_count), 0) FROM agent_experiences"))
        result["experience"] = {
            "total_count": exp_count or 0,
            "active_count": exp_active or 0,
            "inactive_count": exp_inactive or 0,
            "avg_success_weight": round(float(exp_avg_weight or 0), 1),
            "total_fail_count": exp_total_fails or 0,
        }
    except Exception as e:
        logger.warning("Admin overview experience query failed: %s", e)
        result["experience"] = {"error": str(e)}

    # 3. 压缩概览（agent_events 中 compaction 事件）
    try:
        comp_count = await db.scalar(text("SELECT COUNT(*) FROM agent_events WHERE event_type = 'compaction'"))
        comp_total_folded = await db.scalar(text(
            "SELECT COALESCE(SUM((payload->>'folded_count')::int), 0) FROM agent_events WHERE event_type = 'compaction'"
        ))
        hard_truncate = await db.scalar(text(
            "SELECT COUNT(*) FROM agent_events WHERE event_type = 'compaction' AND payload->>'fallback' = 'hard_truncate'"
        ))
        result["compression"] = {
            "compaction_count": comp_count or 0,
            "total_folded_events": comp_total_folded or 0,
            "hard_truncate_count": hard_truncate or 0,
        }
    except Exception as e:
        logger.warning("Admin overview compression query failed: %s", e)
        result["compression"] = {"error": str(e)}

    # 4. 降级概览（agent_events 中 degradation 事件）
    try:
        deg_count = await db.scalar(text("SELECT COUNT(*) FROM agent_events WHERE event_type = 'degradation'"))
        result["degradation"] = {
            "degradation_count": deg_count or 0,
        }
    except Exception as e:
        logger.warning("Admin overview degradation query failed: %s", e)
        result["degradation"] = {"error": str(e)}

    # 5. 对话统计（agent_events）
    try:
        conv_with_events = await db.scalar(text("SELECT COUNT(DISTINCT conversation_id) FROM agent_events"))
        total_events = await db.scalar(text("SELECT COUNT(*) FROM agent_events"))
        user_msg_count = await db.scalar(text("SELECT COUNT(*) FROM agent_events WHERE event_type = 'user_msg'"))
        tool_call_count = await db.scalar(text("SELECT COUNT(*) FROM agent_events WHERE event_type = 'tool_call'"))
        avg_events_per_conv = await db.scalar(text(
            "SELECT COALESCE(ROUND(AVG(cnt)), 0) FROM (SELECT COUNT(*) AS cnt FROM agent_events GROUP BY conversation_id) sub"
        ))
        result["conversations"] = {
            "conversation_count": conv_with_events or 0,
            "total_events": total_events or 0,
            "user_msg_count": user_msg_count or 0,
            "tool_call_count": tool_call_count or 0,
            "avg_events_per_conversation": avg_events_per_conv or 0,
        }
    except Exception as e:
        logger.warning("Admin overview conversation query failed: %s", e)
        result["conversations"] = {"error": str(e)}

    # 6. 粘滞统计（日志搜 stuck）
    try:
        import glob as _glob
        import re as _re
        stuck_count = 0
        log_dir = Path(__file__).resolve().parent.parent.parent / "backend" / "logs"
        if log_dir.exists():
            for log_file in _glob.glob(str(log_dir / "*.log")):
                try:
                    with open(log_file, "r", errors="ignore") as f:
                        for line in f:
                            if "粘滞检测命中" in line:
                                stuck_count += 1
                except Exception:
                    pass
        result["sticky"] = {
            "stuck_detection_count": stuck_count,
        }
    except Exception as e:
        logger.warning("Admin overview sticky query failed: %s", e)
        result["sticky"] = {"error": str(e)}

    # 7. 成本概览（framework_agent_usage_daily）
    try:
        total_today_cost = await db.scalar(text(
            "SELECT COALESCE(SUM(cost), 0) FROM framework_agent_usage_daily WHERE usage_date = CURRENT_DATE"
        ))
        model_costs = await db.execute(text("""
            SELECT model_key, SUM(call_count) AS calls, SUM(prompt_tokens) AS prompt_tokens,
                   SUM(completion_tokens) AS completion_tokens, SUM(cost) AS cost
            FROM framework_agent_usage_daily
            WHERE usage_date = CURRENT_DATE
            GROUP BY model_key ORDER BY cost DESC
        """))
        module_calls = await db.execute(text("""
            SELECT module, SUM(call_count) AS calls, SUM(cost) AS cost
            FROM framework_agent_usage_daily
            WHERE usage_date = CURRENT_DATE
            GROUP BY module ORDER BY cost DESC
        """))
        last_7_days = await db.execute(text("""
            SELECT usage_date, SUM(cost) AS cost
            FROM framework_agent_usage_daily
            WHERE usage_date >= CURRENT_DATE - 7
            GROUP BY usage_date ORDER BY usage_date
        """))
        result["cost"] = {
            "today_total": round(float(total_today_cost or 0), 4),
            "by_model": [
                {"model_key": r[0], "calls": r[1], "prompt_tokens": r[2], "completion_tokens": r[3], "cost": round(float(r[4] or 0), 4)}
                for r in model_costs.fetchall()
            ],
            "by_module": [
                {"module": r[0], "calls": r[1], "cost": round(float(r[2] or 0), 4)}
                for r in module_calls.fetchall()
            ],
            "last_7_days": [
                {"date": str(r[0]), "cost": round(float(r[1] or 0), 4)}
                for r in last_7_days.fetchall()
            ],
        }
    except Exception as e:
        logger.warning("Admin overview cost query failed: %s", e)
        result["cost"] = {"error": str(e)}

    return ApiResponse(data=result)


async def _submit_profile_evolve_task(conversation_id: int, owner_id: int) -> None:
    """提交后台画像进化任务到 SystemTaskQueue（fire-and-forget，异常自愈）。"""
    try:
        from datetime import datetime, timezone
        from app.database import AsyncSessionLocal
        from app.models.system import SystemTaskQueue

        async with AsyncSessionLocal() as db:
            # 检查距上次进化是否超过阈值（节流：距上次进化超过 30 分钟才提交）
            from init_db import ensure_user_profile
            profile = await ensure_user_profile(db, owner_id)
            if profile.evolved_at:
                from datetime import timedelta
                if datetime.now(timezone.utc) - profile.evolved_at < timedelta(minutes=30):
                    return
            task = SystemTaskQueue(
                task_type="profile_evolve",
                parameters=json.dumps({"conversation_id": conversation_id, "owner_id": owner_id}),
                status="pending",
                priority=0,
                module="agent",
                creator_id=owner_id,
            )
            db.add(task)
            await db.commit()
    except Exception as exc:
        logger.warning("_submit_profile_evolve_task failed (non-fatal): %s", exc)


MEMORY_DISTILL_MODEL_KEY = "deepseek-v4-flash"


async def _submit_memory_distill_task(conversation_id: int, owner_id: int, user_content: str, assistant_content: str) -> None:
    """后台记忆蒸馏：从对话中提取值得记住的事实，保存到 memory 模块。

    fire-and-forget，不阻塞主流程。异常只记日志不抛出。
    """
    try:
        from app.database import AsyncSessionLocal
        from app.gateway.router import gateway_router as _gw

        # 用 LLM 从对话中提取关键事实
        distill_messages = [
            {
                "role": "system",
                "content": (
                    "你是一个记忆提取助手。分析以下用户和AI的对话，提取出值得记住的事实性信息。\n\n"
                    "只提取明确的事实（如用户的偏好、重要日期、计划、项目信息、关键决策等）。\n"
                    "忽略闲聊、问候、确认等非事实内容。\n\n"
                    "以 JSON 数组格式输出，每项包含 text 字段：\n"
                    '[\n'
                    '  {"text": "用户偏好简洁的回答风格"},\n'
                    '  {"text": "用户正在开发一个电商项目"}\n'
                    "]\n\n"
                    "如果没有值得记住的事实，输出空数组 []。\n"
                    "只输出 JSON，不要额外文字。"
                ),
            },
            {
                "role": "user",
                "content": f"用户：{user_content[:1000]}\n\nAI：{assistant_content[:1000]}",
            },
        ]
        result = await _gw.chat(messages=distill_messages, profile_key=MEMORY_DISTILL_MODEL_KEY)
        content = result.get("content", "")
        if not content:
            return

        # 解析 JSON
        import json as _jj
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            cleaned = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(cleaned).strip()
        start = content.find("[")
        end = content.rfind("]")
        if start < 0 or end <= start:
            return
        facts = _jj.loads(content[start:end + 1])
        if not isinstance(facts, list) or not facts:
            return

        # 逐条保存到 memory 模块
        for fact in facts:
            text = fact.get("text", "") if isinstance(fact, dict) else str(fact)
            if not text or len(text) < 10:
                continue
            try:
                await call_capability(
                    "memory", "save",
                    {"text": text.strip(), "tags": "auto-distill"},
                    caller=f"user:{owner_id}",
                    caller_role="admin",
                )
            except Exception as save_exc:
                logger.warning("Memory distill save failed (non-fatal): %s", save_exc)

    except Exception as exc:
        logger.warning("_submit_memory_distill_task failed (non-fatal): %s", exc)


# ── 敏感操作审批 API ─────────────────────────────────────────


@router.get("/admin/approvals/pending")
async def list_approvals(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    """列出所有待审批的敏感操作请求。"""
    items = await list_pending_approvals(db)
    return ApiResponse(data=items)


class ApprovalDecision(BaseModel):
    decision: str  # "approved" | "rejected"
    reason: str | None = None


@router.post("/admin/approvals/{approval_id}/resolve")
async def resolve_approval_endpoint(
    approval_id: int,
    body: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    """审批（同意/拒绝）一个等待确认的敏感操作。"""
    if body.decision not in ("approved", "rejected"):
        return ApiResponse(success=False, error="decision must be 'approved' or 'rejected'")
    result = await resolve_approval(db, approval_id, body.decision, user.id, body.reason)
    return ApiResponse(data=result)
