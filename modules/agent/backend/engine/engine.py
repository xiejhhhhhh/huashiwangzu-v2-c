"""engine编排壳：暴露装配上下文()等给 router。批4：compressor、fallback_chain接入。批5：工具编排、三层记忆、快照、skills注入。"""
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services import conversation_service as conv_svc
from ..prompt_seeds import CONTEXT_TOOL_GUIDANCE_KEY
from ..services.runtime_prompt_provider import get_system_prompt as get_runtime_system_prompt
from .budget_allocator import DiminishingBudgetTracker
from .compressor import compress_middle_with_snapshot as _compress_with_snapshot
from .compressor import hard_truncate_tail as _hard_truncate_tail
from .event_store import read_events
from .experience_memory import experience_feedback as _experience_feedback
from .experience_memory import save_experience as _experience_save
from .fallback_chain import chat_stream_with_fallback as _chat_stream_with_fallback
from .fallback_chain import chat_with_fallback as _chat_with_fallback
from .layered_memory import format_static_memory_for_injection as _format_static_memory
from .layered_memory import fuse as _layered_memory_fuse
from .layered_memory import read_static_memory_files as _read_static_memory_files
from .layered_memory import recall as _layered_memory_recall
from .layered_memory import record as _layered_memory_record
from .post_turn_hooks import PostTurnHooks
from .tool_orchestrator import ToolOrchestrator

logger = logging.getLogger("v2.agent").getChild("engine.engine")

# dream 触发节流：每 N 轮对话触发一次
_DREAM_INTERVAL = 5
_COMPRESSION_TOKEN_HEADROOM = 5000


async def assemble_context(
    db: AsyncSession,
    conversation_id: int,
    current_user_input: str,
    profile_key: str,
    owner_id: int,
    agent_code: str = "erp_chat",
) -> tuple[list[dict], dict]:
    """Context assembly pipeline. Delegates to context_pipeline.run_pipeline().

    Each stage is independently testable. See context_pipeline.py for stage details.
    """
    from .context_pipeline import run_pipeline
    return await run_pipeline(db, conversation_id, current_user_input, profile_key, owner_id, agent_code)



async def read_agent_config(db: AsyncSession, agent_code: str) -> dict | None:
    """Read agent config from agent_configs table.

    Returns None if no config found for the given agent_code.
    """
    try:
        from ..models import AgentConfig
        r = await db.execute(
            select(AgentConfig).where(AgentConfig.agent_code == agent_code)
        )
        c = r.scalar_one_or_none()
        if not c:
            return None
        return {
            "agent_code": c.agent_code,
            "agent_name": c.agent_name,
            "provider": c.provider,
            "model": c.model,
            "system_prompt": c.system_prompt,
            "enabled": c.enabled,
            "temperature": c.temperature,
            "top_p": c.top_p,
            "max_tokens": c.max_tokens,
            "timeout_ms": c.timeout_ms,
            "fallback_model": c.fallback_model,
            "fallback_enabled": c.fallback_enabled,
            "max_concurrency": c.max_concurrency,
            "cooldown_seconds": c.cooldown_seconds,
            "retry_count": c.retry_count,
            "daily_call_limit": c.daily_call_limit,
            "daily_budget": c.daily_budget,
            "monthly_budget": c.monthly_budget,
            "response_format": c.response_format,
            "log_prompt_enabled": c.log_prompt_enabled,
            "log_response_enabled": c.log_response_enabled,
            "sensitive_action_policy": c.sensitive_action_policy,
            "updated_by": c.updated_by,
        }
    except Exception as e:
        logger.warning("Failed to read agent config for '%s': %s", agent_code, e)
        return None


# ── 工具调用指引（按模型差异化） ──────────────────────────────────
# 鼓励模型在一次响应中批量返回独立工具调用，减少多轮交互。
_TOOL_CALL_GUIDANCE: dict[str, str] = {
    "deepseek": (
        "【工具调用指引】当需要调用多个互相独立的工具时（例如同时查询多个信息），"
        "请在同一次响应中一并返回所有工具调用（即多个 tool_calls），"
        "不要分多轮逐个调用，这能大幅提升效率。"
    ),
    "gemma": (
        "【工具调用指引】如果需要使用多个工具，尽量在一次响应中同时发起所有独立的工具调用。"
    ),
    "ollama": (
        "【工具调用指引】如果需要使用工具，优先一次性返回所有可并行执行的工具调用。"
    ),
}

_DEFAULT_TOOL_CALL_GUIDANCE = (
    "【工具调用指引】当需要调用多个互相独立的工具时，"
    "请在一次响应中同时返回所有工具调用，不要分多轮逐个调用。"
)


async def _get_tool_call_guidance(db: AsyncSession, profile_key: str) -> str:
    """Resolve model-specific tool call guidance from DB prompt plus model hint."""
    base = await get_runtime_system_prompt(db, CONTEXT_TOOL_GUIDANCE_KEY)
    model_hint = ""
    for prefix, guidance in _TOOL_CALL_GUIDANCE.items():
        if profile_key.startswith(prefix):
            model_hint = guidance
            break
    if not model_hint:
        model_hint = _DEFAULT_TOOL_CALL_GUIDANCE
    return "\n".join(part for part in (base, model_hint) if part)


async def _build_system_content(db: AsyncSession, owner_id: int, conversation_id: int, agent_code: str = "erp_chat", profile_key: str = "") -> str:
    sys_prompt = await conv_svc.get_system_prompt(db)
    ent_prompt = await conv_svc.get_enterprise_prompt(db)
    profile_data = await conv_svc.get_active_user_profile(db, owner_id)
    profile_text = conv_svc._format_profile_text(profile_data)
    layers = []
    total_chars = 0
    MAX_CHARS = 6000  # Total system content limit to prevent bloat

    # Layer 0: Static file memory (zero-latency, deterministic)
    try:
        static_texts = _read_static_memory_files()
        static_injection = _format_static_memory(static_texts)
        if static_injection:
            layers.append(static_injection)
            total_chars += len(static_injection)
    except Exception as e:
        logger.warning("Static memory read failed (non-fatal): %s", e)

    if sys_prompt:
        layers.append(sys_prompt)
        total_chars += len(sys_prompt)
    if ent_prompt:
        layers.append(ent_prompt)
        total_chars += len(ent_prompt)

    # Agent config override: if the agent has a custom system_prompt, append it
    try:
        agent_cfg = await read_agent_config(db, agent_code)
        if agent_cfg and agent_cfg.get("system_prompt"):
            layers.append(f"Agent 配置提示词：\n{agent_cfg['system_prompt']}")
            total_chars += len(layers[-1])
    except Exception as e:
        logger.warning("Failed to read agent config prompt: %s", e)

    if profile_text:
        layers.append(profile_text)
        total_chars += len(profile_text)

    # Profile 2.0 injection: role + enterprise profiles with length control
    try:
        from ..services.profile_service import build_profile_injections
        profile_injection = await build_profile_injections(
            db, owner_id, role_key=None, max_chars=2000,
        )
        if profile_injection and total_chars < MAX_CHARS:
            injection = profile_injection[:MAX_CHARS - total_chars]
            layers.append(injection)
            total_chars += len(injection)
    except Exception as e:
        logger.debug("Profile 2.0 injection failed (non-fatal): %s", e)

    # ── 上下文变量注入（来自之前工具调用的提炼） ──────────────
    try:
        from ..models import AgentConversation
        from .context_vars import format_context_vars_section
        _conv = await db.get(AgentConversation, conversation_id)
        if _conv and _conv.context_vars:
            _cv_section = format_context_vars_section(_conv.context_vars)
            if _cv_section and total_chars < MAX_CHARS:
                layers.append(_cv_section)
                total_chars += len(_cv_section)
    except Exception as e:
        logger.debug("Context vars injection failed (non-fatal): %s", e)

    # ── 工具调用指引（按 profile 差异化） ──────────────────────────
    tool_guidance = await _get_tool_call_guidance(db, profile_key)
    if tool_guidance:
        layers.append(tool_guidance)

    return "\n\n---\n\n".join(layers)


# ── 批5：模块级单例 ──────────────────────────────────────────────

_orchestrator: ToolOrchestrator | None = None
_hooks: PostTurnHooks | None = None
_budget_tracker: DiminishingBudgetTracker | None = None


def get_orchestrator(max_concurrency: int = 8) -> ToolOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ToolOrchestrator(max_concurrency=max_concurrency)
    return _orchestrator


def get_budget_tracker() -> DiminishingBudgetTracker:
    global _budget_tracker
    if _budget_tracker is None:
        _budget_tracker = DiminishingBudgetTracker()
    return _budget_tracker


def get_hooks() -> PostTurnHooks:
    global _hooks
    if _hooks is None:
        _hooks = PostTurnHooks()
        # Start the background maintenance loop on first hook access.
        # This ensures the global hooks lifecycle starts with the first
        # real conversation turn rather than at module import time (which
        # may run before the async event loop is ready).
        from .post_turn_hooks import setup_global_hooks
        setup_global_hooks()
    return _hooks


# ── 已实现接口（批2 事实记忆） ──────────────────────────────

async def record_turn(db: AsyncSession, conversation_id: int, owner_id: int, messages: list[dict]) -> dict:
    """批2：从对话消息中提取事实记忆并保存。调用 memory 模块 save 能力。"""
    try:
        # 从对话中提取关键事实（仅 user 和 assistant 消息）
        memory_texts = []
        for msg in messages[-6:]:  # 只看最近几轮
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and isinstance(content, str) and len(content) > 20:
                memory_texts.append(f"[{role}] {content[:500]}")
        if not memory_texts:
            return {"status": "skipped", "note": "无可提取的记忆内容"}

        combined = "\n\n".join(memory_texts)
        # 用layered_memory客户端保存
        result = await _layered_memory_record(
            text=combined[:2000],
            owner_id=owner_id,
            source="auto-distill",
            conversation_id=conversation_id,
        )
        return result
    except Exception as e:
        logger.warning("记一笔 failed (non-fatal): %s", e)
        return {"status": "fallback", "error": str(e)}


async def compress(db: AsyncSession, conversation_id: int, profile_key: str = "gemma-4") -> dict:
    """批4：事件压缩。调compressor插入 compaction 事件，不删原始事件。"""
    logger.info("压缩 (conv=%s)", conversation_id)
    try:
        all_events = await read_events(db, conversation_id)
        if len(all_events) <= 30:
            return {"status": "skipped", "reason": "事件数不足"}
        result = await _compress_with_snapshot(db, conversation_id, all_events, profile_key=profile_key)
        return result
    except Exception as e:
        logger.warning("compress失败: %s", e)
        try:
            all_events = await read_events(db, conversation_id)
            return await _hard_truncate_tail(db, conversation_id, all_events)
        except Exception as e2:
            return {"status": "error", "error": str(e2)}


async def recall_memory(db: AsyncSession, owner_id: int, query: str) -> list[dict]:
    """批2：语义召回记忆。调用 memory 模块 recall 能力，含顺链扩展。"""
    try:
        results = await _layered_memory_recall(
            owner_id=owner_id,
            query=query,
            limit=5,
            expand_chain=True,
        )
        return results
    except Exception as e:
        logger.warning("召回记忆 failed (non-fatal): %s", e)
        return []


async def fuse_inject(owner_id: int, query: str, memory_ids: list[int], budget_remaining: int) -> str | None:
    """如果预算紧（< MEMORY_FUSE_BUDGET_THRESHOLD），用即时融合压缩多条记忆成简报。

    否则返回 None（直接用总结层概要，省一次调用）。
    """
    if not memory_ids:
        return None
    if budget_remaining is not None and budget_remaining < 2000:
        # 预算紧：融合压缩
        return await _layered_memory_fuse(owner_id, query, memory_ids)
    return None


# 全局 dream 计数器（近似，跨 worker 不精确但够用）
_dream_counter: int = 0


async def trigger_dream(owner_id: int) -> None:
    """每 DREAM_INTERVAL 次调用触发一次 dream（通过 SystemTaskQueue）。"""
    global _dream_counter
    _dream_counter += 1
    if _dream_counter % _DREAM_INTERVAL == 0:
        try:
            from app.database import AsyncSessionLocal
            from app.models.system import SystemTaskQueue

            async with AsyncSessionLocal() as db:
                task = SystemTaskQueue(
                    task_type="memory_dream",
                    parameters=json.dumps({"owner_id": owner_id}),
                    status="pending",
                    priority=0,
                    module="agent",
                    creator_id=owner_id,
                )
                db.add(task)
                await db.commit()
        except Exception as e:
            logger.warning("dream enqueue failed (non-fatal): %s", e)


# ── 批4 韧性：fallback_chain聊天（供 router 替换裸 gateway_router.chat） ──────

async def chat_with_degradation_chain(
    messages: list[dict],
    profile_key: str,
    tools: list[dict] | None = None,
    conversation_id: int | None = None,
) -> dict:
    """用fallback_chain包装模型调用。主模型失败 → fallback_chain → 本地兜底。"""
    try:
        return await _chat_with_fallback(messages, profile_key, tools, conversation_id=conversation_id)
    except Exception as e:
        logger.error("fallback_chainchat全部失败: %s", e)
        return {"error": str(e), "content": f"(模型调用失败：{e})"}


async def chat_stream_with_degradation_chain(
    messages: list[dict],
    profile_key: str,
    tools: list[dict] | None = None,
    conversation_id: int | None = None,
):
    """流式fallback_chain。首包失败可降级；已经开始流式中途断给清晰错误。"""
    try:
        async for event in _chat_stream_with_fallback(messages, profile_key, tools, conversation_id=conversation_id):
            yield event
    except Exception as e:
        logger.error("fallback_chain流式chat全部失败: %s", e)
        yield {"type": "error", "content": f"(流式模型调用失败：{e})"}
    yield {"type": "done"}


# ── 批3 成功经验：蒸馏 + 结算 ──────────────────────────────

async def distill_experience(
    trigger_condition: str,
    steps: list[dict],
    tools_used: list[str] | None = None,
    source_conversation_id: int | None = None,
    owner_id: int = 0,
) -> None:
    """fire-and-forget：对话成功后，把成功路径蒸馏成一条经验存入经验库。

    降级：失败不影响主对话。
    """
    try:
        steps_str = json.dumps(steps, ensure_ascii=False)
        tools_str = json.dumps(tools_used, ensure_ascii=False) if tools_used else None
        await _experience_save(
            trigger_condition=trigger_condition,
            steps=steps_str,
            tools_used=tools_str,
            source_conversation_id=source_conversation_id,
            caller=f"user:{owner_id}" if owner_id else "system:engine",
        )
    except Exception as e:
        logger.warning("蒸馏经验 failed (non-fatal): %s", e)


async def settle_experience(
    experience_id: int,
    success: bool,
    note: str | None = None,
    owner_id: int = 0,
) -> None:
    """fire-and-forget：对话结束后，对用过的经验做成功/失败反馈。

    降级：失败不影响主对话。
    """
    try:
        await _experience_feedback(
            experience_id=experience_id,
            success=success,
            note=note,
            caller=f"user:{owner_id}" if owner_id else "system:engine",
        )
    except Exception as e:
        logger.warning("经验结算 failed (non-fatal): %s", e)
