"""Background task handlers for agent module.

Registered with framework task_worker at module load time:
  - profile_evolve: handle_profile_evolve (from profile_evolve module)
  - memory_dream: _handle_memory_dream
  - memory_distill: _handle_memory_distill
  - agent_execute_slow_tool: _handle_slow_tool
"""

from __future__ import annotations

import json
import logging

from app.services.module_registry import call_capability
from app.services.task_worker import register_task_handler

from ..services import tool_discovery
from ..services.profile_evolve import handle_profile_evolve

logger = logging.getLogger("v2.agent").getChild("handlers.tasks")

MEMORY_DISTILL_MODEL_KEY = "deepseek-v4-flash"


# ── Profile evolve ──

register_task_handler("profile_evolve", handle_profile_evolve)


# ── Memory dream ──

async def _handle_memory_dream(params: dict) -> dict:
    """Handle memory_dream task from queue. Calls dream on memory module."""
    owner_id = params.get("owner_id")
    if not owner_id:
        return {"error": "Missing owner_id"}
    try:
        from ..engine.layered_memory import trigger_dream
        await trigger_dream(owner_id)
        return {"status": "ok", "owner_id": owner_id}
    except Exception as e:
        logger.warning("Memory dream handler failed (non-fatal): %s", e)
        return {"error": str(e)}


register_task_handler("memory_dream", _handle_memory_dream)


# ── Memory distill ──

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


# ── Slow tool execution ──

async def _submit_slow_tool_task(
    conversation_id: int, user_id: int, tool_name: str,
    skill_args: dict, caller: str, caller_role: str,
) -> int:
    """将慢工具提交到 SystemTaskQueue 后台执行。

    Returns: task_id
    """
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
            status="pending", priority=0, module="agent", creator_id=user_id,
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
        if tool_name.startswith("skill_use__"):
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

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            from ..services import conversation_service as conv_svc2
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

            try:
                notify_result = await call_capability(
                    "im", "notify",
                    {
                        "user_id": owner_id,
                        "content": f"✅ 你的后台任务 [{tool_name}] 已完成，请到 AI 助手对话中查看结果。",
                        "title": "后台任务完成",
                    },
                    caller="system:agent_worker",
                    caller_role="admin",
                )
                logger.info("Slow tool notify result: %s", notify_result)
            except Exception as notify_exc:
                logger.warning("Slow tool IM notify failed (non-fatal): %s", notify_exc)

            try:
                from sqlalchemy import select

                from ..models import AgentConversation
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


# ── Workflow mining ──

async def _handle_workflow_mine(params: dict) -> dict:
    """Handle workflow_mine task from SystemTaskQueue."""
    owner_id = params.get("owner_id")
    if not owner_id:
        return {"error": "Missing owner_id"}
    try:
        from app.database import AsyncSessionLocal

        from ..engine.workflow_recipe_service import run_mining_job
        async with AsyncSessionLocal() as db:
            result = await run_mining_job(
                db,
                owner_id=owner_id,
                trajectory_id=params.get("trajectory_id"),
            )
            if result.get("mined", 0) > 0:
                logger.info("Workflow mining: mined %d recipes for owner %s", result["mined"], owner_id)
            return result
    except Exception as e:
        logger.warning("Workflow mining handler failed: %s", e)
        return {"error": str(e)}


register_task_handler("workflow_mine", _handle_workflow_mine)


# ── Async context compaction ──

async def _handle_context_compact(params: dict) -> dict:
    """Background handler: compress events up to until_event_id.

    Runs the LLM-based compressor in the background worker, then atomically
    writes a ``ready`` compaction record.  The unique constraint on
    ``(conversation_id, until_event_id, generation)`` ensures that only one
    worker's result is accepted — retries that would produce a duplicate
    silently skip.
    """
    conversation_id = params.get("conversation_id")
    owner_id = params.get("owner_id")
    until_event_id = params.get("until_event_id")
    profile_key = params.get("profile_key", "deepseek-v4-flash")

    if not conversation_id or not owner_id or not until_event_id:
        return {"error": "Missing required params"}

    from datetime import datetime, timezone

    from app.database import AsyncSessionLocal
    from sqlalchemy import select
    from sqlalchemy import update as sa_update
    from sqlalchemy.exc import IntegrityError

    from ..engine.budget_allocator import (
        RESERVED_OUTPUT_TOKENS,
        estimate_one_message,
        get_effective_context_budget,
    )
    from ..engine.compressor import CHEAP_MODEL_KEY, MAX_SUMMARY_CHARS, compress_middle
    from ..engine.context_injectors.tool_result_reducer import reduce as reduce_tool_results
    from ..engine.event_store import _project_event_list
    from ..models import AgentContextCompaction, AgentConversation, AgentEvent

    def _estimate_projected(messages: list[dict]) -> int:
        return sum(estimate_one_message(message) for message in messages)

    def _combine_summaries(previous: str, current: str) -> str:
        combined = "\n\n".join(part for part in (previous.strip(), current.strip()) if part)
        if len(combined) <= MAX_SUMMARY_CHARS:
            return combined
        marker = "\n\n[摘要中间已截断]\n\n"
        half = (MAX_SUMMARY_CHARS - len(marker)) // 2
        return (combined[:half] + marker + combined[-half:])[:MAX_SUMMARY_CHARS]

    async def _mark_failed(compaction_id: int, error: str) -> None:
        await db.rollback()
        await db.execute(
            sa_update(AgentContextCompaction)
            .where(
                AgentContextCompaction.id == compaction_id,
                AgentContextCompaction.status == "building",
            )
            .values(
                status="failed",
                error=error[:1000],
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        # Highest watermark wins even if an older task completes later.
        existing = await db.execute(
            select(AgentContextCompaction)
            .where(
                AgentContextCompaction.conversation_id == conversation_id,
                AgentContextCompaction.status == "ready",
            )
            .order_by(
                AgentContextCompaction.until_event_id.desc(),
                AgentContextCompaction.generation.desc(),
                AgentContextCompaction.id.desc(),
            )
            .limit(1)
        )
        previous_ready = existing.scalar_one_or_none()
        if previous_ready and previous_ready.until_event_id >= until_event_id:
            logger.info("Compaction already ready for conv=%s until=%s — skipping", conversation_id, until_event_id)
            return {"status": "skipped", "reason": "already ready"}

        # Read events up to watermark
        r = await db.execute(
            select(AgentEvent)
            .where(
                AgentEvent.conversation_id == conversation_id,
                AgentEvent.id <= until_event_id,
            )
            .order_by(AgentEvent.id)
        )
        events = list(r.scalars().all())
        if not events:
            return {"status": "skipped", "reason": "no events"}
        captured_event_ids = [event.id for event in events]

        projected, _ = reduce_tool_results(_project_event_list(events))
        token_before = _estimate_projected(projected)
        effective_budget, _ = get_effective_context_budget(profile_key)
        history_budget = max(effective_budget - RESERVED_OUTPUT_TOKENS, 0)
        if effective_budget > 0 and token_before <= history_budget:
            logger.info(
                "Compaction skipped within budget: conv=%s tokens=%d budget=%d",
                conversation_id, token_before, history_budget,
            )
            return {"status": "skipped", "reason": "within budget"}

        # Create building record
        compaction = AgentContextCompaction(
            owner_id=owner_id,
            conversation_id=conversation_id,
            until_event_id=until_event_id,
            generation=0,
            status="building",
            token_before=token_before,
            started_at=datetime.now(timezone.utc),
        )
        db.add(compaction)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            logger.info("Compaction duplicate claimed by another worker: conv=%s until=%s", conversation_id, until_event_id)
            return {"status": "skipped", "reason": "duplicate task"}
        await db.refresh(compaction)
        compaction_id = compaction.id

        previous_folded_ids = set(previous_ready.folded_event_ids or []) if previous_ready else set()
        try:
            # The background path must never append a legacy compaction event:
            # only the ready row is visible to request-time projection.
            result = await compress_middle(
                db,
                conversation_id,
                events,
                CHEAP_MODEL_KEY,
                persist_event=False,
                already_folded_ids=previous_folded_ids,
            )
        except Exception as exc:
            logger.error("Compaction %d failed: %s", compaction_id, exc)
            await _mark_failed(compaction_id, str(exc))
            return {"error": str(exc)}

        if result.get("status") == "compressed":
            new_folded_ids = result.get("folded_event_ids")
            if not isinstance(new_folded_ids, list):
                error = "compressor returned invalid folded_event_ids"
                await _mark_failed(compaction_id, error)
                return {"error": error}

            folded_ids = sorted(previous_folded_ids | set(new_folded_ids))
            summary = _combine_summaries(
                previous_ready.summary or "" if previous_ready else "",
                str(result.get("summary") or ""),
            )
            after_events = [event for event in events if event.id not in set(folded_ids)]
            after_messages, _ = reduce_tool_results(_project_event_list(after_events))
            if summary:
                after_messages.insert(0, {"role": "system", "content": "[历史摘要] " + summary})
            token_after = _estimate_projected(after_messages)

            try:
                # Close any pre-LLM transaction, then verify that rollback/edit
                # did not replace the history while this worker was summarizing.
                await db.rollback()
                current_ids_result = await db.execute(
                    select(AgentEvent.id)
                    .where(
                        AgentEvent.conversation_id == conversation_id,
                        AgentEvent.id <= until_event_id,
                    )
                    .order_by(AgentEvent.id)
                )
                current_event_ids = list(current_ids_result.scalars().all())
                conversation_result = await db.execute(
                    select(AgentConversation.status).where(
                        AgentConversation.id == conversation_id,
                        AgentConversation.owner_id == owner_id,
                    )
                )
                conversation_status = conversation_result.scalar_one_or_none()
                if current_event_ids != captured_event_ids or conversation_status != "active":
                    reason = "history changed while compaction was building"
                    await _mark_failed(compaction_id, reason)
                    return {"status": "skipped", "reason": reason}

                r2 = await db.execute(
                    sa_update(AgentContextCompaction)
                    .where(
                        AgentContextCompaction.id == compaction_id,
                        AgentContextCompaction.status == "building",
                    )
                    .values(
                        status="ready",
                        summary=summary,
                        folded_event_ids=folded_ids,
                        token_after=token_after,
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                if r2.rowcount == 0:
                    await db.rollback()
                    logger.info("Compaction %d invalidated or race lost", compaction_id)
                    return {"status": "skipped", "reason": "race lost"}
                await db.commit()
                logger.info(
                    "Context compaction ready: conv=%s until=%s folded=%s before=%d after=%d",
                    conversation_id, until_event_id, len(folded_ids), token_before, token_after,
                )
                return {"status": "ready", "compaction_id": compaction_id}
            except Exception as exc:
                await _mark_failed(compaction_id, str(exc))
                return {"error": str(exc)}
        else:
            reason = str(result.get("reason", "unknown"))
            await _mark_failed(compaction_id, reason)
            return {"status": "failed", "reason": reason}


register_task_handler("agent_context_compact", _handle_context_compact)


async def _submit_memory_distill_task(
    conversation_id: int, owner_id: int,
    user_content: str, assistant_content: str,
) -> None:
    """后台记忆蒸馏：从对话中提取值得记住的事实，保存到 memory 模块。

    fire-and-forget，不阻塞主流程。异常只记日志不抛出。
    """
    try:
        from app.gateway.router import gateway_router as _gw

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

        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            cleaned = [line for line in lines if not line.strip().startswith("```")]
            content = "\n".join(cleaned).strip()
        start = content.find("[")
        end = content.rfind("]")
        if start < 0 or end <= start:
            return
        facts = json.loads(content[start:end + 1])
        if not isinstance(facts, list) or not facts:
            return

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
