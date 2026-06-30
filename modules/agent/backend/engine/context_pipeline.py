"""上下文管线编排壳：将 Agent 上下文组装拆为显式 stage。

Phase 1 目标：在保持 behavior 完全一致的前提下，用 stage 标记替代 flat function。
后续 phase 将每个 stage 逐步抽到独立文件中。
"""
import logging
import os
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..prompt_seeds import (
    CONTEXT_CITATION_RULES_KEY,
    CONTEXT_TOOL_GUIDANCE_KEY,
    ENTERPRISE_PROMPT_KEY,
    SYSTEM_BASE_PROMPT_KEY,
)
from ..services import conversation_service as conv_svc
from ..services.runtime_prompt_provider import RuntimePromptProvider
from .budget_allocator import assemble_context as _budget_assemble_context
from .budget_allocator import estimate_tokens, get_context_budget
from .compressor import compress_middle_with_snapshot as _compress_with_snapshot
from .compressor import hard_truncate_tail as _hard_truncate_tail
from .event_store import project_to_messages, read_events
from .skills_loader import find_skills as _find_skills
from .skills_loader import format_skills_for_prompt as _format_skills
from .skills_loader import match_skills as _match_skills
from .skills_loader import resolve_skill_priority as _resolve_skill_priority
from .thinking_router import route_thinking_level

logger = logging.getLogger("v2.agent").getChild("engine.pipeline")

_COMPRESSION_TOKEN_HEADROOM = 5000


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


# =====================================================================
# Stage 1: Resolve agent config and effective profile key
# =====================================================================
def _resolve_effective_profile(agent_cfg: dict | None, profile_key: str) -> str:
    if agent_cfg and agent_cfg.get("model"):
        return agent_cfg["model"]
    return profile_key


# =====================================================================
# Stage 2: Project events → model messages
# =====================================================================
async def _project_history(
    db: AsyncSession,
    conversation_id: int,
) -> tuple[list[dict], list[dict]]:
    projected: list[dict] = []
    all_events: list[dict] = []
    try:
        projected = await project_to_messages(db, conversation_id)
        all_events = await read_events(db, conversation_id) if projected else []
    except Exception as e:
        logger.warning("投影事件失败，回退空投影: %s", e)
    return projected, all_events


# =====================================================================
# Stage 3: Thinking routing
# =====================================================================
async def _route_thinking(
    db: AsyncSession,
    current_user_input: str,
    owner_id: int,
    conversation_id: int,
    profile_key: str,
    agent_code: str,
) -> tuple[dict, dict | None]:
    thinking_route = None
    try:
        thinking_route = await route_thinking_level(
            db,
            current_user_input,
            owner_id=owner_id,
            conversation_id=conversation_id,
            profile_key=profile_key,
            agent_code=agent_code,
        )
    except Exception as e:
        logger.warning("Thinking routing failed（non-fatal）: %s", e)

    if thinking_route:
        diag = {
            "thinking_level": thinking_route.level,
            "thinking_source": thinking_route.source,
            "thinking_confidence": thinking_route.confidence,
            "thinking_reason": thinking_route.reason,
        }
    else:
        diag = {
            "thinking_level": "medium",
            "thinking_source": "fallback",
            "thinking_confidence": 0.0,
            "thinking_reason": "routing unavailable",
        }
    return diag, thinking_route


# =====================================================================
# Stage 4: Build system content (wraps _build_system_content)
# =====================================================================
async def _build_system_content(
    db: AsyncSession,
    owner_id: int,
    conversation_id: int,
    agent_code: str = "erp_chat",
    profile_key: str = "",
) -> str:
    """Build the system prompt from profile, thinking suggestion, skills, context vars."""
    from ..models import AgentConversation
    from .context_vars import format_context_vars_section

    try:
        _profile = conv_svc.get_profile_by_key(db, profile_key) if profile_key else None
    except Exception:
        _profile = None

    layers: list[str] = []
    total_chars = 0
    MAX_CHARS = 10000
    prompt_provider = RuntimePromptProvider(db)

    for key in (SYSTEM_BASE_PROMPT_KEY, ENTERPRISE_PROMPT_KEY):
        prompt_text = (await prompt_provider.get_system_prompt(key)).strip()
        if prompt_text and total_chars < MAX_CHARS:
            layers.append(prompt_text)
            total_chars += len(prompt_text)

    user_prompts = await prompt_provider.get_user_prompts(owner_id)
    if user_prompts and total_chars < MAX_CHARS:
        user_section = "\n\n".join(
            f"### {item.title}\n{item.content.strip()}"
            for item in user_prompts[:5]
            if item.content and item.content.strip()
        )
        if user_section:
            layers.append("## 用户自定义提示词\n" + user_section)
            total_chars += len(layers[-1])

    profile_data = await conv_svc.get_active_user_profile(db, owner_id)
    profile_text = conv_svc._format_profile_text(profile_data)
    if profile_text and total_chars < MAX_CHARS:
        layers.append(profile_text)
        total_chars += len(profile_text)

    if _profile and _profile.system_prompt:
        layers.append(_profile.system_prompt.strip())
        total_chars += len(layers[-1])

    # ── 上下文变量注入（来自之前工具调用的提炼） ──────────────
    try:
        _conv = await db.get(AgentConversation, conversation_id)
        if _conv and _conv.context_vars:
            _cv_section = format_context_vars_section(_conv.context_vars)
            if _cv_section and total_chars < MAX_CHARS:
                layers.append(_cv_section)
                total_chars += len(_cv_section)
    except Exception as e:
        logger.debug("Context vars injection failed (non-fatal): %s", e)

    # ── 工具调用指引（按 profile 差异化） ──────────────────────────
    if _profile and _profile.tool_usage_guide:
        guide = _profile.tool_usage_guide.strip()
    else:
        guide = (await prompt_provider.get_system_prompt(CONTEXT_TOOL_GUIDANCE_KEY)).strip()
    if guide and total_chars < MAX_CHARS:
        layers.append("\n## 工具调用指引\n" + guide)
        total_chars += len(layers[-1])

    # ── 引用规范提示（减少幻觉，放末尾以增加模型注意力） ────
    cite_prompt = (await prompt_provider.get_system_prompt(CONTEXT_CITATION_RULES_KEY)).strip()
    if cite_prompt and total_chars < MAX_CHARS:
        layers.append("\n## 引用强制规则（必须遵守）\n" + cite_prompt)
        total_chars += len(layers[-1])

    return "\n\n".join(layers).strip()


# =====================================================================
# Stage 5: Compress if budget exceeded
# =====================================================================
async def _compress_context(
    db: AsyncSession,
    conversation_id: int,
    all_events: list[dict],
    projected: list[dict],
    estimated_total: int,
    effective_profile_key: str,
) -> list[dict]:
    budget = get_context_budget(effective_profile_key)
    if (
        budget is not None
        and estimated_total > budget + _COMPRESSION_TOKEN_HEADROOM
        and len(all_events) > 30
    ):
        try:
            logger.info("预算超限(est=%d > budget=%d), 触发压缩(含快照)", estimated_total, budget)
            result = await _compress_with_snapshot(
                db, conversation_id, all_events, projected, effective_profile_key
            )
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
    return projected


# =====================================================================
# Stage 6: Inject skills into system content
# =====================================================================
def _inject_skills(system_content: str) -> str:
    try:
        skill_base = os.environ.get("SKILLS_DIR", "data/skills")
        all_skills = _find_skills(skill_base, scope="global")
        workspace_path = os.environ.get("CURRENT_PATH", "")
        if workspace_path:
            workspace_skills_dir = os.path.join(workspace_path, ".agent-skills")
            if os.path.isdir(workspace_skills_dir):
                ws_skills = _find_skills(workspace_skills_dir, scope="workspace")
                all_skills.extend(ws_skills)
        all_skills = _resolve_skill_priority(all_skills)
        matched = _match_skills(all_skills, workspace_path)
        skill_injection = _format_skills(matched)
        if skill_injection and system_content:
            system_content += "\n\n---\n\n<available_skills>\n" + skill_injection + "\n</available_skills>"
    except Exception as e:
        logger.warning("skills注入失败（non-fatal）: %s", e)
    return system_content


# =====================================================================
# Stage 7: Token budget assembly
# =====================================================================
def _budget_assembly(
    projected: list[dict],
    system_content: str,
    current_user_input: str,
    effective_profile_key: str,
) -> tuple[list[dict], dict]:
    try:
        messages, diagnosis = _budget_assemble_context(
            projected, system_content, current_user_input, effective_profile_key
        )
    except Exception as e:
        logger.warning("预算装配失败，回退原始投影+截尾: %s", e)
        messages = [{"role": "system", "content": system_content}]
        messages.extend(projected[-48:] if len(projected) > 48 else projected)
        diagnosis = {"error": str(e), "fallback": "原始投影截尾"}
    return messages, diagnosis


# =====================================================================
# Stage 8: Inject context layers into the first system message
# =====================================================================
async def _inject_context_layers(
    messages: list[dict],
    diagnosis: dict,
    current_user_input: str,
    owner_id: int,
    db: AsyncSession,
) -> tuple[list[dict], dict]:
    """Apply three-layer memory, workflow strategy, success experience, and workflow recipe injection.

    Each injector follows the same contract: inject(messages, diagnosis, ...) → (messages, diagnosis).
    New injectors can be added by importing a new module and calling it here.
    """
    from .context_injectors import experience as _exp
    from .context_injectors import three_layer_memory
    from .context_injectors import workflow as _wf
    from .context_injectors.workflow_recipe import inject as _recipe_inject

    messages, diagnosis = await three_layer_memory.inject(
        messages, diagnosis, owner_id=owner_id, current_user_input=current_user_input, logger=logger,
    )
    messages, diagnosis = _wf.inject(messages, diagnosis, current_user_input=current_user_input)
    messages, diagnosis = await _exp.inject(
        messages, diagnosis, current_user_input=current_user_input, owner_id=owner_id, logger=logger,
    )
    messages, diagnosis = await _recipe_inject(
        messages, diagnosis, db=db, owner_id=owner_id, current_input=current_user_input,
    )
    return messages, diagnosis


# =====================================================================
# Main pipeline orchestrator
# =====================================================================
async def run_pipeline(
    db: AsyncSession,
    conversation_id: int,
    current_user_input: str,
    profile_key: str,
    owner_id: int,
    agent_code: str = "erp_chat",
) -> tuple[list[dict], dict]:
    """New context assembly pipeline: stage-by-stage orchestrator.

    Behavior is identical to the original assemble_context().
    Each stage is a separate callable for independent testing.
    """
    _t0 = time.monotonic()

    # Stage 1: Resolve agent config
    _t1 = time.monotonic()
    agent_cfg = None
    try:
        agent_cfg = await read_agent_config(db, agent_code)
    except Exception as e:
        logger.warning("读取 agent config 失败: %s", e)
    effective_profile_key = _resolve_effective_profile(agent_cfg, profile_key)
    logger.info("[PIPELINE_TIMING] Stage 1 (agent config): %dms", round((time.monotonic() - _t1) * 1000))

    # Stage 2: Project events → model messages
    _t2 = time.monotonic()
    projected, all_events = await _project_history(db, conversation_id)
    logger.info("[PIPELINE_TIMING] Stage 2 (project history): %dms, events=%d", round((time.monotonic() - _t2) * 1000), len(projected or []))

    # Stage 2b: Reduce tool results
    _t2b = time.monotonic()
    from .context_injectors.tool_result_reducer import reduce as _reduce_tool_results
    projected, reduce_diag = _reduce_tool_results(projected)
    logger.info("Tool result reducer: %d compressed, %d chars saved [%dms]",
                 reduce_diag.get("tool_results_compressed", 0),
                 reduce_diag.get("total_chars_saved", 0),
                 round((time.monotonic() - _t2b) * 1000))

    # Stage 3: Thinking routing
    _t3 = time.monotonic()
    thinking_diag, thinking_route = await _route_thinking(
        db, current_user_input, owner_id, conversation_id, effective_profile_key, agent_code,
    )
    logger.info("[PIPELINE_TIMING] Stage 3 (thinking routing): %dms, level=%s",
                round((time.monotonic() - _t3) * 1000),
                thinking_diag.get("thinking_level", "?"))

    # Stage 4: Build system content
    _t4 = time.monotonic()
    system_content = await _build_system_content(
        db, owner_id, conversation_id, agent_code, profile_key=effective_profile_key,
    )
    logger.info("[PIPELINE_TIMING] Stage 4 (build system content): %dms, chars=%d",
                round((time.monotonic() - _t4) * 1000), len(system_content))

    if thinking_route and thinking_route.level and thinking_route.level != "medium":
        system_content += f"\n\n【思考深度建议】建议思考等级：{thinking_route.level}"

    # Stage 5: Compress if budget exceeded
    _t5 = time.monotonic()
    projected_tokens = (
        sum(max(estimate_tokens([m]), 0) for m in projected[-100:])
        if projected
        else 0
    )
    system_tokens = max(len(system_content) // 2, 0)
    input_tokens = max(len(current_user_input) // 2, 0)
    estimated_total = system_tokens + input_tokens + projected_tokens + 4096

    projected = await _compress_context(
        db, conversation_id, all_events, projected, estimated_total, effective_profile_key,
    )
    logger.info("[PIPELINE_TIMING] Stage 5 (compress): %dms", round((time.monotonic() - _t5) * 1000))

    # Stage 6: Inject skills into system content
    _t6 = time.monotonic()
    system_content = _inject_skills(system_content)
    logger.info("[PIPELINE_TIMING] Stage 6 (inject skills): %dms", round((time.monotonic() - _t6) * 1000))

    # Stage 7: Token budget assembly
    _t7 = time.monotonic()
    messages, diagnosis = _budget_assembly(projected, system_content, current_user_input, effective_profile_key)
    logger.info("[PIPELINE_TIMING] Stage 7 (budget assembly): %dms", round((time.monotonic() - _t7) * 1000))
    diagnosis.update(thinking_diag)
    diagnosis.update(reduce_diag)
    diagnosis["agent_code"] = agent_code
    diagnosis["effective_profile_key"] = effective_profile_key

    # Stage 8: Inject context layers (memory, experience, workflow, recipe)
    _t8 = time.monotonic()
    messages, diagnosis = await _inject_context_layers(messages, diagnosis, current_user_input, owner_id, db)
    logger.info("[PIPELINE_TIMING] Stage 8 (context layers injection): %dms", round((time.monotonic() - _t8) * 1000))

    logger.info("[PIPELINE_TIMING] run_pipeline TOTAL: %dms", round((time.monotonic() - _t0) * 1000))
    return messages, diagnosis
