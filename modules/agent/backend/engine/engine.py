"""engine编排壳：暴露装配上下文()等给 router。批4：compressor、fallback_chain接入。"""
import asyncio
import json
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .. import conversation_service as conv_svc
from .event_store import read_events, project_to_messages, record_event
from .budget_allocator import assemble_context as _budget_assemble_context, estimate_tokens, get_context_budget
from .layered_memory import record as _layered_memory_record, recall as _layered_memory_recall, fuse as _layered_memory_fuse
from .experience_memory import match_experience as _experience_match, save_experience as _experience_save, experience_feedback as _experience_feedback, format_injection as _experience_format
from .compressor import compress_middle as _compress_middle, hard_truncate_tail as _hard_truncate_tail
from .fallback_chain import chat_with_fallback as _chat_with_fallback, chat_stream_with_fallback as _chat_stream_with_fallback

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
    # Read agent config for parameter overrides
    agent_cfg = None
    try:
        agent_cfg = await read_agent_config(db, agent_code)
    except Exception as e:
        logger.warning("读取 agent config 失败: %s", e)

    # Resolve effective profile_key: agent config model > caller profile_key > default
    effective_profile_key = profile_key
    if agent_cfg and agent_cfg.get("model"):
        effective_profile_key = agent_cfg["model"]

    try:
        projected = await project_to_messages(db, conversation_id)
        all_events = await read_events(db, conversation_id) if projected else []
    except Exception as e:
        logger.warning("投影事件失败，回退空投影: %s", e)
        projected = []
        all_events = []

    # ── 批4：预算超限时调compressor ──────────────────────────────────────────
    try:
        system_content = await _build_system_content(db, owner_id, agent_code)
    except Exception as e:
        logger.warning("构建系统提示词失败: %s", e)
        system_content = "You are a helpful AI assistant."

    budget = get_context_budget(effective_profile_key)
    projected_tokens = sum(
        max(estimate_tokens([m]), 0) for m in projected[-100:]
    ) if projected else 0
    system_tokens = max(len(system_content) // 2, 0)
    input_tokens = max(len(current_user_input) // 2, 0)
    estimated_total = system_tokens + input_tokens + projected_tokens + 4096

    if budget is not None and estimated_total > budget + _COMPRESSION_TOKEN_HEADROOM and len(all_events) > 30:
        try:
            logger.info("预算超限(est=%d > budget=%d), 触发压缩", estimated_total, budget)
            result = await _compress_middle(db, conversation_id, all_events, effective_profile_key)
            if result.get("status") == "compressed":
                projected = await project_to_messages(db, conversation_id)
                logger.info("压缩后投影完毕, 事件数=%d", len(projected))
        except Exception as e:
            logger.warning("压缩失败（降级到硬截断）: %s", e)
            try:
                await _hard_truncate_tail(db, conversation_id, all_events)
                projected = await project_to_messages(db, conversation_id)
            except Exception as e2:
                logger.warning("硬截断也失败: %s", e2)

    try:
        messages, diagnosis = _budget_assemble_context(projected, system_content, current_user_input, effective_profile_key)
    except Exception as e:
        logger.warning("预算装配失败，回退原始投影+截尾: %s", e)
        messages = [{"role": "system", "content": system_content}]
        messages.extend(projected[-48:] if len(projected) > 48 else projected)
        diagnosis = {"error": str(e), "fallback": "原始投影截尾"}
    diagnosis["agent_code"] = agent_code
    diagnosis["effective_profile_key"] = effective_profile_key

    # ── 成功经验注入（批3）：语义匹配当前输入，注入 known success path ──
    try:
        matched = await _experience_match(current_user_input, limit=2, caller=f"user:{owner_id}")
        injection = _experience_format(matched)
        if injection and messages:
            for msg in messages:
                if msg["role"] == "system":
                    msg["content"] += injection
                    break
            diagnosis["experience_injected"] = [e["id"] for e in matched if e.get("id")]
            diagnosis["experience_injection"] = "成功注入" if injection else "无命中"
        else:
            diagnosis["experience_injection"] = "无命中"
    except Exception as e:
        logger.warning("经验注入失败（降级，不阻塞）: %s", e)
        diagnosis["experience_injection"] = f"降级: {e}"

    return messages, diagnosis


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


async def _build_system_content(db: AsyncSession, owner_id: int, agent_code: str = "erp_chat") -> str:
    sys_prompt = await conv_svc.get_system_prompt(db)
    ent_prompt = await conv_svc.get_enterprise_prompt(db)
    profile_data = await conv_svc.get_active_user_profile(db, owner_id)
    profile_text = conv_svc._format_profile_text(profile_data)
    layers = []
    if sys_prompt:
        layers.append(sys_prompt)
    if ent_prompt:
        layers.append(ent_prompt)

    # Agent config override: if the agent has a custom system_prompt, append it
    try:
        agent_cfg = await read_agent_config(db, agent_code)
        if agent_cfg and agent_cfg.get("system_prompt"):
            layers.append(f"Agent 配置提示词：\n{agent_cfg['system_prompt']}")
    except Exception as e:
        logger.warning("Failed to read agent config prompt: %s", e)

    if profile_text:
        layers.append(profile_text)
    return "\n\n---\n\n".join(layers)


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
        result = await _compress_middle(db, conversation_id, all_events, profile_key)
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
            import json
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
