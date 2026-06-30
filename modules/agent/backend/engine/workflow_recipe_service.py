"""Workflow recipe service: CRUD, scoring, mining, and injection helpers.

This is the main persistence layer for per-user mined workflow recipes.
Each recipe is a structured description of the shortest known tool chain
for a given user intent, along with scoring and provenance metadata.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentWorkflowRecipe

logger = logging.getLogger("v2.agent").getChild("workflow_recipe")

# ── Scoring constants ──
_RECIPE_DECAY_DAYS = 7          # half-life for recency scoring
_SUCCESS_WEIGHT_SCALE = 20      # max success_weight before lowering boost
_CONFIDENCE_MIN = 0.3            # below this: do not inject
_TOP_N_INJECT = 2                # max recipes to inject per turn

# Domain intent aliases for intranet/desktop agent tasks.
# These are intentionally compact and rule-based. Embedding recall can be added later.
_INTENT_ALIASES: dict[str, set[str]] = {
    "desktop_file": {"桌面", "文件", "列表", "有什么", "打开", "查看", "xlsx", "docx", "excel", "word"},
    "open_file": {"打开", "查看", "读取", "内容", "文件", "文档", "桌面", "预览"},
    "generate_excel": {"excel", "xlsx", "表格", "生成", "导出", "输出", "汇总", "摘要"},
    "replace_file": {"替换", "覆盖", "更新", "旧文件", "新文件", "桌面", "文件"},
    "refresh_desktop": {"刷新", "桌面", "列表", "显示", "更新"},
    "summarize_doc": {"总结", "摘要", "提炼", "概括", "文档", "内容", "分析"},
    "search_knowledge": {"搜索", "查询", "知识库", "资料", "找一下", "检索"},
    "create_doc": {"生成", "创建", "写", "文档", "docx", "word", "报告"},
    "edit_doc": {"修改", "编辑", "改", "润色", "更新", "文档", "内容"},
    "run_code": {"运行", "执行", "python", "脚本", "命令", "terminal", "终端"},
}


def _normalize_text(text: str) -> str:
    return (text or "").lower().replace(" ", "").replace("　", "")


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    text = _normalize_text(text)
    if not text:
        return set()
    if len(text) <= n:
        return {text}
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _keyword_score(query: str, target: str) -> float:
    q = _normalize_text(query)
    t = _normalize_text(target)
    if not q or not t:
        return 0.0
    score = 0.0
    if q in t or t in q:
        score = max(score, 0.75)
    score = max(score, _jaccard(_char_ngrams(q), _char_ngrams(t)))
    return min(score, 1.0)


def _intent_alias_score(query: str, target: str) -> float:
    text = _normalize_text(query + target)
    best = 0.0
    for words in _INTENT_ALIASES.values():
        q_hits = sum(1 for w in words if w in _normalize_text(query))
        t_hits = sum(1 for w in words if w in _normalize_text(target))
        if q_hits and t_hits:
            best = max(best, min(1.0, (q_hits + t_hits) / (len(words) + 1)))
        elif q_hits >= 2 and any(w in text for w in words):
            best = max(best, min(0.6, q_hits / max(len(words), 1)))
    return best


def recipe_match_score(current_input: str, recipe: AgentWorkflowRecipe) -> float:
    """Hybrid match score for workflow recipes.

    Combines:
      - exact/substring similarity
      - Chinese character n-gram Jaccard
      - domain alias overlap
      - tool-name hints
    """
    targets = [
        recipe.intent_label or "",
        recipe.trigger_condition or "",
        recipe.name or "",
        recipe.description or "",
        " ".join(str(t) for t in (recipe.tools_used or [])),
    ]
    best = 0.0
    for target in targets:
        if not target:
            continue
        best = max(best, _keyword_score(current_input, target))
        best = max(best, _intent_alias_score(current_input, target))
    return round(min(best, 1.0), 4)


# =====================================================================
# Scoring
# =====================================================================

def _recency_score(last_used_at: datetime | None) -> float:
    """Time-decay factor: 0 (unused) → 1 (just used). Half-life 7 days."""
    if not last_used_at:
        return 0.0
    days = (datetime.now(timezone.utc) - last_used_at).total_seconds() / 86400
    return max(0.1, pow(0.5, days / _RECIPE_DECAY_DAYS))


def compute_confidence(recipe: AgentWorkflowRecipe) -> float:
    """Score a recipe for injection ranking.

    Factors:
      - success_weight (capped)
      - fail_count (penalty)
      - avg_duration (lower = better)
      - avg_tool_count (lower = better)
      - recency
    """
    success = min(recipe.success_weight or 0, _SUCCESS_WEIGHT_SCALE)
    failure_penalty = (recipe.fail_count or 0) * 2.0

    # Speed factor: 1.0 at ≤2s, 0.5 at 10s, 0 at >20s
    dur = recipe.avg_duration_ms or 30000
    speed = max(0.0, 1.0 - (dur / 20000))

    # Tool factor: 1.0 at ≤2 tools, 0.5 at 6 tools
    tools = recipe.avg_tool_count or 5
    tool_eff = max(0.0, 1.0 - ((tools - 1) / 8))

    recency = _recency_score(recipe.last_used_at)
    status_ok = 1.0 if recipe.enabled and recipe.status == "published" else 0.5

    base = max(0.0, success - failure_penalty)
    score = (
        base * 0.35 +
        speed * 0.25 +
        tool_eff * 0.15 +
        recency * 0.15 +
        status_ok * 0.10
    )
    return min(round(score, 4), 10.0)


# =====================================================================
# CRUD
# =====================================================================

async def get_by_owner(
    db: AsyncSession,
    owner_id: int,
    limit: int = 20,
    enabled_only: bool = True,
) -> list[AgentWorkflowRecipe]:
    """List recipes for a user, ordered by confidence desc."""
    stmt = (
        select(AgentWorkflowRecipe)
        .where(AgentWorkflowRecipe.owner_id == owner_id)
        .order_by(desc(AgentWorkflowRecipe.confidence))
        .limit(limit)
    )
    if enabled_only:
        stmt = stmt.where(AgentWorkflowRecipe.enabled)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(db: AsyncSession, recipe_id: int) -> AgentWorkflowRecipe | None:
    result = await db.execute(
        select(AgentWorkflowRecipe).where(AgentWorkflowRecipe.id == recipe_id)
    )
    return result.scalar_one_or_none()


async def upsert_recipe(
    db: AsyncSession,
    owner_id: int,
    name: str,
    intent_label: str,
    trigger_condition: str,
    steps: list[dict],
    tools_used: list[str],
    source_conversation_id: int | None = None,
    source_trajectory_id: int | None = None,
    avg_duration_ms: float | None = None,
    avg_tool_count: float | None = None,
) -> int:
    """Create or update a recipe. If a recipe with same (owner_id, intent_label)
    exists, increment success_weight and update other fields."""
    existing = await db.execute(
        select(AgentWorkflowRecipe)
        .where(AgentWorkflowRecipe.owner_id == owner_id)
        .where(AgentWorkflowRecipe.intent_label == intent_label)
        .limit(1)
    )
    existing_recipe = existing.scalar_one_or_none()

    if existing_recipe:
        # Durable queue delivery is at-least-once. Reprocessing the same
        # newest trajectory must not inflate recipe weight/version.
        if (
            source_trajectory_id is not None
            and existing_recipe.source_trajectory_id == source_trajectory_id
        ):
            return existing_recipe.id
        existing_recipe.success_weight = (existing_recipe.success_weight or 0) + 1.0
        existing_recipe.fail_count = 0
        existing_recipe.avg_duration_ms = avg_duration_ms
        existing_recipe.avg_tool_count = avg_tool_count
        existing_recipe.last_used_at = datetime.now(timezone.utc)
        existing_recipe.steps = steps
        existing_recipe.tools_used = tools_used
        existing_recipe.trigger_condition = trigger_condition
        existing_recipe.source_conversation_id = source_conversation_id
        existing_recipe.source_trajectory_id = source_trajectory_id
        existing_recipe.version = (existing_recipe.version or 1) + 1
        existing_recipe.status = "published"
        existing_recipe.confidence = compute_confidence(existing_recipe)
        recipe_id = existing_recipe.id
    else:
        recipe = AgentWorkflowRecipe(
            owner_id=owner_id,
            name=name,
            description="",
            intent_label=intent_label,
            trigger_condition=trigger_condition,
            steps=steps,
            tools_used=tools_used,
            status="published",
            version=1,
            success_weight=1.0,
            fail_count=0,
            avg_duration_ms=avg_duration_ms,
            avg_tool_count=avg_tool_count,
            last_used_at=datetime.now(timezone.utc),
            confidence=0.0,
            source_conversation_id=source_conversation_id,
            source_trajectory_id=source_trajectory_id,
            enabled=True,
        )
        db.add(recipe)
        await db.flush()
        recipe_id = recipe.id
        recipe.confidence = compute_confidence(recipe)

    await db.commit()
    logger.info("Recipe upserted: id=%s owner=%s label=%s", recipe_id, owner_id, intent_label)
    return recipe_id


async def record_failure(db: AsyncSession, recipe_id: int):
    """Increment fail_count and re-compute confidence."""
    recipe = await get_by_id(db, recipe_id)
    if not recipe:
        return
    recipe.fail_count = (recipe.fail_count or 0) + 1
    recipe.confidence = compute_confidence(recipe)
    await db.commit()


async def disable_recipe(db: AsyncSession, recipe_id: int):
    recipe = await get_by_id(db, recipe_id)
    if recipe:
        recipe.enabled = False
        await db.commit()


# =====================================================================
# Match & Inject helpers
# =====================================================================

async def match_recipes(
    db: AsyncSession,
    owner_id: int,
    current_input: str,
    top_n: int = _TOP_N_INJECT,
) -> list[AgentWorkflowRecipe]:
    """Find recipes for this user matching the current input.

    Simple matching: check if any token from current_input appears in
    the recipe intent_label or trigger_condition.
    """
    recipes = await get_by_owner(db, owner_id, limit=50, enabled_only=True)
    if not recipes:
        return []

    scored: list[tuple[float, AgentWorkflowRecipe]] = []

    for r in recipes:
        match_score = recipe_match_score(current_input, r)
        if match_score <= 0:
            continue

        # Gate weak matches unless the recipe itself is very strong.
        if match_score < 0.18 and (r.confidence or 0) < 0.6:
            continue

        combined = match_score * 0.6 + (r.confidence or 0) * 0.4
        scored.append((combined, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_n]]


def format_recipe_for_injection(recipes: list[AgentWorkflowRecipe]) -> str:
    """Format matched recipes as a compact markdown block for system prompt."""
    if not recipes:
        return ""

    lines: list[str] = ["\n【工作流建议（后台挖掘）】"]
    for r in recipes:
        name = r.name or r.intent_label
        lines.append("")
        lines.append(f"### {name}")
        if r.description:
            lines.append(f"{r.description}")
        if r.steps:
            lines.append("")
            lines.append("推荐步骤：")
            for i, step in enumerate(r.steps, 1):
                if isinstance(step, dict):
                    step_text = step.get("step") or step.get("action") or json.dumps(step, ensure_ascii=False)
                else:
                    step_text = str(step)
                lines.append(f"{i}. {step_text}")
        if r.tools_used:
            lines.append("")
            lines.append(f"使用工具：{' → '.join(str(t) for t in r.tools_used)}")
        lines.append(f"（成功率 {r.success_weight or 0:.0f} 次 · 平均耗时 {r.avg_duration_ms / 1000:.1f}s · 置信度 {r.confidence:.2f}）")

    return "\n".join(lines)


# =====================================================================
# Mining helpers
# =====================================================================

def _text_intent_similarity(text_a: str, text_b: str) -> float:
    """Pure text-to-text intent similarity for grouping trajectories.

    Uses keyword scoring + char n-gram Jaccard + intent alias overlap.
    This is separate from ``recipe_match_score()`` which compares
    input text to a ``AgentWorkflowRecipe`` model instance.
    """
    score = _keyword_score(text_a, text_b)
    score = max(score, _intent_alias_score(text_a, text_b))
    return round(min(score, 1.0), 4)


async def run_mining_job(
    db: AsyncSession,
    owner_id: int,
    **kwargs,
) -> dict[str, Any]:
    """Mine workflow recipes from recent successful trajectories.

    This is a placeholder rule-based miner. It scans recent trajectory
    records and identifies high-success, low-tool-count paths.
    """
    from ..models import AgentTrajectoryRecord

    result = await db.execute(
        select(AgentTrajectoryRecord)
        .where(AgentTrajectoryRecord.owner_id == owner_id)
        .where(AgentTrajectoryRecord.error_occurred == False)  # noqa: E712
        .where(AgentTrajectoryRecord.user_correction.is_(None))
        .order_by(desc(AgentTrajectoryRecord.id))
        .limit(100)
    )
    trajectories = list(result.scalars().all())
    if not trajectories:
        return {"mined": 0, "reason": "no_successful_trajectories"}

    # Group by semantic intent similarity using keyword + alias scoring
    # Note: we compare text-to-text here (not a TrajectoryRecord to a Recipe).
    groups: dict[str, list[AgentTrajectoryRecord]] = {}
    _assigned: set[int] = set()
    for t in trajectories:
        if t.id in _assigned:
            continue
        group = [t]
        _assigned.add(t.id)
        for t2 in trajectories:
            if t2.id in _assigned:
                continue
            score = _text_intent_similarity(t.user_input or "", t2.user_input or "")
            if score >= 0.3:
                group.append(t2)
                _assigned.add(t2.id)
        # Use the most common phrasing as group key
        key = max((t.user_input or "")[:80] for t in group)
        groups[key] = group

    mined = 0
    for intent, trajs in groups.items():
        if len(trajs) < 2:
            continue  # need at least 2 successes to mine

        sum(1 for t in trajs if not t.error_occurred)
        sum(1 for t in trajs if t.error_occurred)
        avg_dur = sum((t.duration_ms or 0) for t in trajs) / len(trajs) if trajs else None

        # Extract tool names from tool_calls
        all_tools: list[str] = []
        all_steps: list[dict] = []
        for t in trajs:
            if t.tool_calls:
                for tc in t.tool_calls[:]:
                    if isinstance(tc, dict):
                        name = tc.get("name") or tc.get("function", {}).get("name", "")
                        if name:
                            all_tools.append(name)
                        step = {"step": name, "arguments": tc.get("arguments", {}),
                                "tool_call_id": tc.get("tool_call_id")}
                        all_steps.append(step)

        avg_tool_count = len(all_tools) / len(trajs) if trajs else None

        if all_tools:
            await upsert_recipe(
                db,
                owner_id=owner_id,
                name=intent,
                intent_label=intent,
                trigger_condition=intent,
                steps=all_steps[:10],
                tools_used=list(dict.fromkeys(all_tools))[:10],
                source_conversation_id=trajs[0].conversation_id,
                source_trajectory_id=trajs[0].id,
                avg_duration_ms=avg_dur,
                avg_tool_count=avg_tool_count,
            )
            mined += 1

    return {"mined": mined, "processed": len(groups)}
