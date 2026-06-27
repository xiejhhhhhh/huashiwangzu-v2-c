"""Thinking level routing for agent turns.

Rule-first, history-second, main-model-fallback third.
The recommendation is advisory and is written back to history.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass

from app.gateway import service as gateway_service
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .experience_memory import match_experience as _match_experience

logger = logging.getLogger("v2.agent").getChild("engine.thinking_router")

THINKING_LEVELS = ("none", "low", "medium", "high", "deep")
DEFAULT_THINKING_LEVEL = "medium"

GREETING_PATTERNS = (
    r"^你好[啊呀哈]*$",
    r"^hi[!！。,\.\s]*$",
    r"^hello[!！。,\.\s]*$",
    r"^在吗[?？!！。,\.\s]*$",
    r"^谢谢[!！。,\.\s]*$",
    r"^ok[!！。,\.\s]*$",
    r"^好的[!！。,\.\s]*$",
    r"^收到[!！。,\.\s]*$",
)

RULE_LEVEL_PATTERNS: list[tuple[str, str]] = [
    (r"^(你好|hi|hello|在吗|谢谢|好的|ok|收到)[!！。,\.\s]*$", "none"),
    (r"^(是吗|对吗|行吗|可以吗|确认一下)[?？!！。,\.\s]*$", "low"),
    (r"^(帮我看看|帮我查一下|解释一下|什么意思|怎么回事)[?？!！。,\.\s]*$", "low"),
    (r"^(帮我分析|帮我规划|帮我设计|帮我比较|帮我做计划|给我方案|详细分析|深入分析)", "high"),
]

IMPLICIT_FEEDBACK_HINTS: list[tuple[str, str, float, float]] = [
    (r"(太简单|太浅|不够|再想|重新想|深入|细一点|更详细|展开|补充|继续分析)", "high", 1.0, 1.0),
    (r"(太复杂|太长|太啰嗦|简短点|直接说|别展开|不用分析|少说点)", "low", 1.0, 1.0),
    (r"(不对|错了|不是这个|看错|理解错|没说到点上)", "medium", 1.0, 1.5),
]


@dataclass(slots=True)
class ThinkingRouteResult:
    level: str
    source: str
    confidence: float = 0.0
    reason: str = ""
    fallback_used: bool = False


async def route_thinking_level(
    db: AsyncSession,
    user_input: str,
    *,
    owner_id: int,
    conversation_id: int,
    profile_key: str,
    agent_code: str = "erp_chat",
) -> ThinkingRouteResult:
    text_input = (user_input or "").strip()
    if not text_input:
        return ThinkingRouteResult(level="none", source="rule", confidence=1.0, reason="empty input")

    rule_result = _match_rule(text_input)
    if rule_result:
        return rule_result

    signal_result = await _match_signal_history(db, text_input, owner_id=owner_id)
    if signal_result:
        return signal_result

    history_result = await _match_history(text_input, owner_id=owner_id)
    if history_result:
        return history_result

    llm_result = await _ask_llm_once(db, text_input, profile_key=profile_key, agent_code=agent_code)
    llm_result.reason = llm_result.reason or "llm fallback"
    await _store_thinking_history(
        db,
        query_text=text_input,
        level=llm_result.level,
        confidence=llm_result.confidence,
        owner_id=owner_id,
        conversation_id=conversation_id,
        source=llm_result.source,
        reason=llm_result.reason,
    )
    return llm_result


async def record_thinking_feedback(
    db: AsyncSession,
    *,
    query_text: str,
    recommended_level: str,
    owner_id: int,
    conversation_id: int,
    source: str,
    confidence: float,
    used_level: str | None = None,
    accepted: bool | None = None,
    reason: str = "",
) -> int | None:
    return await _store_thinking_history(
        db,
        query_text=query_text,
        level=used_level or recommended_level,
        confidence=confidence,
        owner_id=owner_id,
        conversation_id=conversation_id,
        source=source,
        reason=reason,
        accepted=accepted,
    )


def _match_rule(user_input: str) -> ThinkingRouteResult | None:
    for pattern, level in RULE_LEVEL_PATTERNS:
        if re.search(pattern, user_input, flags=re.IGNORECASE):
            confidence = 1.0 if level == "none" else 0.95 if level == "low" else 0.9
            return ThinkingRouteResult(level=level, source="rule", confidence=confidence, reason=f"matched {pattern}")
    if len(user_input) <= 2:
        return ThinkingRouteResult(level="none", source="rule", confidence=1.0, reason="very short input")
    return None


async def record_implicit_thinking_signal(
    db: AsyncSession,
    *,
    owner_id: int,
    conversation_id: int,
    current_input: str,
) -> None:
    text_input = (current_input or "").strip()
    signal = _infer_implicit_signal(text_input)
    if not signal:
        return
    expected_level, signal_value, strength, reason = signal
    previous = await _latest_thinking_record(db, owner_id=owner_id, conversation_id=conversation_id)
    if not previous:
        return
    previous_id = int(previous.get("id") or 0)
    previous_level = _normalize_level(previous.get("thinking_level"))
    previous_query = str(previous.get("query_text") or "")
    negative_delta = -0.6 * strength
    positive_delta = 0.8 * strength
    await _store_thinking_signal(
        db,
        thinking_level_id=previous_id,
        owner_id=owner_id,
        conversation_id=conversation_id,
        query_text=previous_query,
        thinking_level=previous_level,
        signal_type="implicit_correction",
        signal_value=signal_value,
        score_delta=negative_delta,
        reason=reason,
        metadata={"current_input": text_input[:500], "expected_level": expected_level},
    )
    if expected_level != previous_level:
        await _store_thinking_signal(
            db,
            thinking_level_id=previous_id,
            owner_id=owner_id,
            conversation_id=conversation_id,
            query_text=previous_query,
            thinking_level=expected_level,
            signal_type="implicit_expected_level",
            signal_value=signal_value,
            score_delta=positive_delta,
            reason=reason,
            metadata={"current_input": text_input[:500], "previous_level": previous_level},
        )


async def _match_signal_history(db: AsyncSession, user_input: str, *, owner_id: int) -> ThinkingRouteResult | None:
    try:
        rows = await db.execute(
            text(
                """
                SELECT query_text, thinking_level, score_delta,
                       EXTRACT(EPOCH FROM (NOW() - created_at)) AS age_seconds
                FROM agent_thinking_level_signals
                WHERE owner_id = :owner_id
                ORDER BY id DESC
                LIMIT 80
                """
            ),
            {"owner_id": owner_id},
        )
    except Exception as exc:
        logger.warning("Match thinking signal history failed: %s", exc)
        return None

    scores: dict[str, float] = defaultdict(float)
    best_reason = ""
    best_score = 0.0
    for row in rows.mappings().all():
        level = _normalize_level(row.get("thinking_level"))
        if level not in THINKING_LEVELS:
            continue
        similarity = _text_similarity(user_input, str(row.get("query_text") or ""))
        if similarity < 0.15:
            continue
        age_seconds = float(row.get("age_seconds") or 0.0)
        recency = max(0.2, 1.0 / (1.0 + age_seconds / 604800.0))
        delta = float(row.get("score_delta") or 0.0)
        score = similarity * recency * delta
        scores[level] += score
        if abs(score) > abs(best_score):
            best_score = score
            best_reason = f"signal sim={similarity:.2f} recency={recency:.2f} delta={delta:.2f}"

    positive_scores = {level: score for level, score in scores.items() if score > 0.05}
    if not positive_scores:
        return None
    level = max(positive_scores, key=positive_scores.get)
    confidence = min(max(positive_scores[level], 0.0), 1.0)
    return ThinkingRouteResult(level=level, source="signals", confidence=confidence, reason=best_reason)


async def _match_history(user_input: str, *, owner_id: int) -> ThinkingRouteResult | None:
    # Reuse existing experience store as a lightweight recall source.
    experiences = await _match_experience(user_input, limit=3, caller=f"user:{owner_id}")
    if not experiences:
        return None

    scores: dict[str, float] = {}
    best_reason = ""
    best_confidence = 0.0
    for exp in experiences:
        level = _normalize_level(exp.get("thinking_level") or exp.get("metadata", {}).get("thinking_level"))
        if level not in THINKING_LEVELS:
            continue
        similarity = float(exp.get("similarity", 0.0) or 0.0)
        weight = float(exp.get("net_weight", exp.get("success_weight", 1) or 1) or 1)
        score = similarity * max(weight, 0.1)
        scores[level] = scores.get(level, 0.0) + score
        if score > best_confidence:
            best_confidence = score
            best_reason = f"history match id={exp.get('id')} sim={similarity:.2f} weight={weight:.2f}"

    if not scores:
        return None

    level = max(scores, key=scores.get)
    confidence = min(max(scores[level], 0.0), 1.0)
    return ThinkingRouteResult(level=level, source="history", confidence=confidence, reason=best_reason)


async def _ask_llm_once(
    db: AsyncSession,
    user_input: str,
    *,
    profile_key: str,
    agent_code: str,
) -> ThinkingRouteResult:
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个思维等级路由器。你的任务不是回答问题，而是判断这次请求应该使用哪种思考深度。"
                    "可选值只有 none / low / medium / high / deep。"
                    "如果只是问候、确认、短回复，输出 none。"
                    "如果是需要简单解释、澄清、轻量查询，输出 low。"
                    "如果需要标准回答，输出 medium。"
                    "如果需要分析、比较、规划、设计，输出 high。"
                    "如果是复杂、多步骤、需要多轮推理，输出 deep。"
                    "只输出 JSON：{\"thinking_level\": \"...\", \"confidence\": 0.0, \"reason\": \"...\"}"
                ),
            },
            {"role": "user", "content": user_input[:2000]},
        ]
        result = await gateway_service.chat(messages=messages, profile_key=profile_key)
        if result.get("error"):
            raise RuntimeError(result.get("error"))
        content = (result.get("content") or "").strip()
        parsed = _parse_llm_json(content)
        level = _normalize_level(parsed.get("thinking_level"))
        confidence = _safe_float(parsed.get("confidence"), default=0.5)
        reason = str(parsed.get("reason", ""))[:300]
        if level not in THINKING_LEVELS:
            level = DEFAULT_THINKING_LEVEL
        return ThinkingRouteResult(level=level, source="llm", confidence=confidence, reason=reason, fallback_used=False)
    except Exception as exc:
        logger.warning("Thinking level LLM fallback failed: %s", exc)
        return ThinkingRouteResult(
            level=DEFAULT_THINKING_LEVEL,
            source="fallback",
            confidence=0.0,
            reason=str(exc)[:200],
            fallback_used=True,
        )


async def _store_thinking_history(
    db: AsyncSession,
    *,
    query_text: str,
    level: str,
    confidence: float,
    owner_id: int,
    conversation_id: int,
    source: str,
    reason: str,
    accepted: bool | None = None,
) -> int | None:
    try:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_thinking_levels (
                    id BIGSERIAL PRIMARY KEY,
                    owner_id INTEGER NOT NULL,
                    conversation_id BIGINT NOT NULL,
                    query_text TEXT NOT NULL,
                    thinking_level VARCHAR(16) NOT NULL,
                    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    source VARCHAR(16) NOT NULL DEFAULT 'rule',
                    reason TEXT DEFAULT '',
                    accepted BOOLEAN,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        result = await db.execute(
            text(
                """
                INSERT INTO agent_thinking_levels
                (owner_id, conversation_id, query_text, thinking_level, confidence, source, reason, accepted)
                VALUES (:owner_id, :conversation_id, :query_text, :thinking_level, :confidence, :source, :reason, :accepted)
                RETURNING id
                """
            ),
            {
                "owner_id": owner_id,
                "conversation_id": conversation_id,
                "query_text": query_text[:4000],
                "thinking_level": level,
                "confidence": confidence,
                "source": source,
                "reason": reason[:1000],
                "accepted": accepted,
            },
        )
        thinking_level_id = result.scalar_one_or_none()
        await db.commit()
        return int(thinking_level_id) if thinking_level_id is not None else None
    except Exception as exc:
        await db.rollback()
        logger.warning("Store thinking history failed: %s", exc)
        return None


async def _latest_thinking_record(
    db: AsyncSession,
    *,
    owner_id: int,
    conversation_id: int,
) -> dict[str, object] | None:
    try:
        result = await db.execute(
            text(
                """
                SELECT id, query_text, thinking_level, source, confidence, reason
                FROM agent_thinking_levels
                WHERE owner_id = :owner_id AND conversation_id = :conversation_id
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"owner_id": owner_id, "conversation_id": conversation_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None
    except Exception as exc:
        logger.warning("Load latest thinking record failed: %s", exc)
        return None


async def _store_thinking_signal(
    db: AsyncSession,
    *,
    thinking_level_id: int | None,
    owner_id: int,
    conversation_id: int,
    query_text: str,
    thinking_level: str,
    signal_type: str,
    signal_value: float,
    score_delta: float,
    reason: str,
    metadata: dict[str, object],
) -> None:
    try:
        await db.execute(
            text(
                """
                INSERT INTO agent_thinking_level_signals
                (thinking_level_id, owner_id, conversation_id, query_text, thinking_level,
                 signal_type, signal_value, score_delta, reason, metadata)
                VALUES (:thinking_level_id, :owner_id, :conversation_id, :query_text, :thinking_level,
                        :signal_type, :signal_value, :score_delta, :reason, CAST(:metadata AS jsonb))
                """
            ),
            {
                "thinking_level_id": thinking_level_id,
                "owner_id": owner_id,
                "conversation_id": conversation_id,
                "query_text": query_text[:4000],
                "thinking_level": thinking_level,
                "signal_type": signal_type,
                "signal_value": signal_value,
                "score_delta": score_delta,
                "reason": reason[:1000],
                "metadata": json.dumps(metadata, ensure_ascii=False),
            },
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("Store thinking signal failed: %s", exc)


def _infer_implicit_signal(user_input: str) -> tuple[str, float, float, str] | None:
    for pattern, expected_level, signal_value, strength in IMPLICIT_FEEDBACK_HINTS:
        if re.search(pattern, user_input, flags=re.IGNORECASE):
            return expected_level, signal_value, strength, f"matched {pattern}"
    return None


def _text_similarity(left: str, right: str) -> float:
    left_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", (left or "").lower()))
    right_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", (right or "").lower()))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return overlap / union if union else 0.0


def _parse_llm_json(content: str) -> dict:
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                return {}
    return {}


def _normalize_level(level: object) -> str:
    value = str(level or "").strip().lower()
    return value if value in THINKING_LEVELS else DEFAULT_THINKING_LEVEL


def _safe_float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
