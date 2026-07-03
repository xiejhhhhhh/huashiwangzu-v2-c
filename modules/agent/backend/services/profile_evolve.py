"""Profile evolution handler — background task for auto-evolving user profiles.

Registered as a task handler via `register_task_handler("profile_evolve", ...)`.
Consumed by the framework worker: analyzes recent user conversations using
the LLM gateway to extract/update tone, taboos, focus areas, and habits.

Key design:
- Incremental: only analyze messages newer than last evolved_at.
- Signal-first: new observations go to agent_profile_signals pool first.
- Threshold-gated: only apply to profile when enough high-confidence signals.
- Semantic merge: use LLM to merge, not simple set union.
- Capped fields: taboos<=15, focus<=30, habits<=20.
"""
import json
import logging
from ast import literal_eval
from datetime import datetime, timezone
from typing import Any

from app.database import AsyncSessionLocal
from app.gateway.router import gateway_router
from sqlalchemy import select

logger = logging.getLogger("v2.agent").getChild("profile_evolve")

# 用于分析画像的 system prompt
ANALYSIS_SYSTEM_PROMPT = (
    "你是一个用户行为分析助手。分析以下对话历史，提取该用户的个人沟通特征。\n\n"
    "请以 JSON 格式输出，包含以下字段：\n"
    "{\n"
    '  "tone": "用户偏好的语气风格描述（如简洁、详细、正式、随意等）",\n'
    '  "taboos": ["用户不愿意谈或不喜欢的主题列表"],\n'
    '  "focus": ["用户经常关注或询问的领域列表"],\n'
    '  "habits": ["用户的沟通习惯，如喜欢举例子、经常追问细节等"]\n'
    "}\n\n"
    "如果没有足够信息推断某个字段，用空字符串或空数组。只输出 JSON，不要额外文字。"
)

# 合并旧画像 + 新分析 → 更新后的画像（语义归并）
MERGE_SYSTEM_PROMPT = (
    "你是一个用户画像更新助手。你将收到：\n"
    "1. 旧画像（该用户的已有特征）\n"
    "2. 新分析（从最近对话提取的新特征）\n\n"
    "请合并两者，输出更新的 JSON 画像。新分析的内容优先，旧画像中未被新分析覆盖的保留。\n"
    "重要：合并时如果多条描述意思相近或重复（如同是'喜欢追问XX'的不同变体），"
    "请合并成一条最准确、最完整的表述，不要保留重复项。\n"
    "字段：tone（字符串）、taboos（数组）、focus（数组）、habits（数组）。只输出 JSON，不要额外文字。"
)

# 确定性合并：同义项检测 + 上限截断
MERGE_DETERMINISTIC_SYSTEM_PROMPT = (
    "你是一个用户画像同义归并助手。你会收到一个用户画像的字段（taboos/focus/habits）列表。\n"
    "请检测哪些条目意思相近或重复（如\"喜欢追问细节\"和\"经常追问细节和边界\"），"
    "将它们合并成一条最准确、最完整的表述，去掉多余重复项。\n"
    "输出合并后的 JSON 数组，只输出数组，不要额外文字。"
)

EVOLVE_MODEL_KEY = "deepseek-v4-flash"
MERGE_MODEL_KEY = "deepseek-v4-flash"
MAX_ANALYSIS_MESSAGES = 20
SIGNAL_CONFIDENCE_THRESHOLD = 0.6  # minimum confidence to auto-apply signal
SIGNAL_REPEAT_THRESHOLD = 2  # how many similar signals needed to qualify

# Field caps
MAX_TABOOS = 15
MAX_FOCUS = 30
MAX_HABITS = 20


def _make_fingerprint(msg_ids: list[int], item: str) -> str:
    """Create a deterministic fingerprint from source message IDs + item text."""
    import hashlib
    raw = f"{'_'.join(str(m) for m in sorted(msg_ids))}:{item.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()


async def _add_profile_watermark(
    db,
    signal_model: Any,
    *,
    owner_id: int,
    conversation_id: int,
    msg_ids: list[int],
    reason: str = "",
) -> bool:
    """Persist a per-conversation watermark so best-effort evolve jobs can skip bad batches."""
    if not msg_ids:
        return False
    watermark_fp = _make_fingerprint(msg_ids, "__watermark__")
    watermark_exists = await db.execute(
        select(signal_model.id)
        .where(
            signal_model.owner_id == owner_id,
            signal_model.conversation_id == conversation_id,
            signal_model.signal_data["fingerprint"].as_string() == watermark_fp,
        )
        .limit(1)
    )
    if watermark_exists.scalar_one_or_none() is not None:
        return False
    signal_data = {
        "fingerprint": watermark_fp,
        "last_msg_id": max(msg_ids),
    }
    if reason:
        signal_data["reason"] = reason
    db.add(signal_model(
        owner_id=owner_id,
        signal_type="watermark",
        target_profile_type="user",
        signal_data=signal_data,
        confidence=1.0,
        source="auto_evolve",
        conversation_id=conversation_id,
        applied=True,
        applied_at=datetime.now(timezone.utc),
    ))
    return True


async def handle_profile_evolve(params: dict) -> dict:
    """Profile evolution task handler (incremental, signal-first, fingerprint-deduped).

    框架 worker 调用此函数。params 包含 conversation_id 和 owner_id.
    """
    conversation_id = params.get("conversation_id")
    owner_id = params.get("owner_id")
    if not conversation_id or not owner_id:
        return {"error": "Missing conversation_id or owner_id"}

    logger.info("Profile evolve starting for user %s, conv %s", owner_id, conversation_id)

    async with AsyncSessionLocal() as db:
        from ..models import AgentProfileSignal, AgentUserProfile

        # Get current profile
        profile_result = await db.execute(
            select(AgentUserProfile).where(AgentUserProfile.owner_id == owner_id)
        )
        profile = profile_result.scalar_one_or_none()
        if not profile:
            return {"error": "No profile found", "owner_id": owner_id}

        # Get the last processed message id as watermark (per conversation)
        from ..models import AgentMessage
        watermark_signal = await db.execute(
            select(AgentProfileSignal)
            .where(
                AgentProfileSignal.owner_id == owner_id,
                AgentProfileSignal.source == "auto_evolve",
                AgentProfileSignal.conversation_id == conversation_id,
            )
            .order_by(AgentProfileSignal.id.desc())
            .limit(1)
        )
        last_signal = watermark_signal.scalar_one_or_none()
        last_msg_id = 0
        if last_signal and isinstance(last_signal.signal_data, dict):
            last_msg_id = last_signal.signal_data.get("last_msg_id", 0)

        # Get messages in this conversation we haven't processed yet
        msg_query = select(AgentMessage.id, AgentMessage.role, AgentMessage.content).where(
            AgentMessage.owner_id == owner_id,
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.id > last_msg_id,
        ).order_by(AgentMessage.id.asc())
        msg_result = await db.execute(msg_query)
        rows = msg_result.all()

        if not rows:
            logger.info("Profile evolve: no new messages since msg_id %s for user %s, conv %s",
                        last_msg_id, owner_id, conversation_id)
            return {"status": "skipped", "reason": "no_new_evidence", "owner_id": owner_id}

        # Process oldest unseen messages first so a large backlog is consumed
        # in bounded batches without silently skipping evidence.
        processed_rows = rows[:MAX_ANALYSIS_MESSAGES]
        new_msg_ids = [r[0] for r in processed_rows]
        # Build analysis text from new messages
        chat_text = "\n".join(
            f"{r[1]}: {(r[2] or '')[:500]}"
            for r in processed_rows
            if r[1] in ("user", "assistant")
        )

        # Build analysis messages
        chat_messages = [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": "对话历史：\n" + chat_text},
        ]

        # Call LLM for analysis
        result = await gateway_router.chat(
            messages=chat_messages,
            profile_key=EVOLVE_MODEL_KEY,
        )

        content = result.get("content", "")
        if not content:
            logger.warning("Profile evolve: empty LLM response for user %s", owner_id)
            return {
                "status": "failed",
                "error": "empty_llm_response",
                "owner_id": owner_id,
                "retryable": True,
            }

        new_analysis = _parse_profile_json(content)
        if not new_analysis:
            logger.warning("Profile evolve: failed to parse LLM response for user %s: %s", owner_id, content[:200])
            return {
                "status": "failed",
                "error": "unparseable_llm_profile_json",
                "owner_id": owner_id,
                "retryable": True,
            }

        # Write new observations as low-confidence signals with fingerprint dedup
        signal_count = 0
        for key in ("taboos", "focus", "habits"):
            items = new_analysis.get(key, [])
            if not isinstance(items, list):
                continue
            for item in items[:5]:
                if not isinstance(item, str) or not item.strip():
                    continue
                fp = _make_fingerprint(new_msg_ids, item)
                existing = await db.execute(
                    select(AgentProfileSignal.id)
                    .where(
                        AgentProfileSignal.owner_id == owner_id,
                        AgentProfileSignal.signal_data["fingerprint"].as_string() == fp,
                    )
                    .limit(1)
                )
                if existing.scalar_one_or_none():
                    continue
                signal = AgentProfileSignal(
                    owner_id=owner_id,
                    signal_type=key,
                    target_profile_type="user",
                    signal_data={"text": item.strip(), "fingerprint": fp, "last_msg_id": max(new_msg_ids)},
                    confidence=0.4,
                    source="auto_evolve",
                    conversation_id=conversation_id,
                    applied=False,
                )
                db.add(signal)
                signal_count += 1

        # Persist an explicit per-conversation watermark even when the model
        # emits no list observations. Otherwise the same messages are analyzed
        # forever and tone-only/empty analyses never advance.
        await _add_profile_watermark(
            db,
            AgentProfileSignal,
            owner_id=owner_id,
            conversation_id=conversation_id,
            msg_ids=new_msg_ids,
        )
        await db.commit()
        logger.info("Profile evolve: recorded %d new signals for user %s", signal_count, owner_id)

        # Check signal pool for threshold-qualifying changes
        signals_result = await db.execute(
            select(AgentProfileSignal).where(
                AgentProfileSignal.owner_id == owner_id,
                AgentProfileSignal.applied == False,  # noqa: E712
            )
        )
        pending_signals = list(signals_result.scalars().all())

        qualified = await _check_signal_threshold(db, owner_id, pending_signals)
        if not qualified:
            logger.info("Profile evolve: no threshold-qualified signals for user %s", owner_id)
            return {
                "status": "signal_collected",
                "owner_id": owner_id,
                "new_signals": signal_count,
                "pending_signals": len(pending_signals),
                "applied": False,
            }

        # Build consolidated analysis from qualified signals
        consolidated = {"tone": new_analysis.get("tone", ""), "taboos": [], "focus": [], "habits": []}
        for q in qualified:
            key = q.signal_type
            sd = q.signal_data if isinstance(q.signal_data, dict) else {}
            text = sd.get("text", "")
            if key in consolidated and isinstance(consolidated[key], list) and text:
                consolidated[key].append(text)

        # Merge with existing profile
        old_profile_data = _db_profile_to_dict(profile.profile_data)
        merged = await _merge_profiles(old_profile_data, consolidated)

        # Deduplicate semantically within each list
        merged = await _deduplicate_profile(merged)

        # Apply field caps (sorted by confidence, evidence count, recency)
        merged = await _apply_caps(merged, pending_signals)

        # Check if anything changed
        old_json = json.dumps(old_profile_data, ensure_ascii=False, sort_keys=True) if isinstance(old_profile_data, dict) else "{}"
        new_json = json.dumps(merged, ensure_ascii=False, sort_keys=True)
        if old_json == new_json:
            logger.info("Profile evolve: no change for user %s (merged identical)", owner_id)
            await _mark_signals_applied(db, qualified)
            return {"status": "no_change", "owner_id": owner_id, "version": profile.version}

        # Update profile
        profile.profile_data = merged
        profile.version = (profile.version or 1) + 1
        profile.evolved_at = datetime.now(timezone.utc)
        await db.commit()
        await _mark_signals_applied(db, qualified)

        logger.info(
            "Profile evolved for user %s: version %d -> %d",
            owner_id, profile.version - 1, profile.version,
        )

    return {
        "status": "ok",
        "owner_id": owner_id,
        "version": profile.version,
        "profile_summary": {k: v for k, v in merged.items() if v},
        "signals_applied": len(qualified),
    }


async def _check_signal_threshold(
    db: AsyncSessionLocal,
    owner_id: int,
    pending_signals: list,
) -> list:
    """Check pending signals for threshold qualification.

    A signal qualifies if:
    - individual confidence >= SIGNAL_CONFIDENCE_THRESHOLD, OR
    - SIGNAL_REPEAT_THRESHOLD+ signals share the same or substring-equivalent text.

    Each fingerprint counts as at most ONE evidence source — running the
    same analysis twice on the same messages does not generate two
    independent pieces of evidence.
    """
    qualified = []
    for signal in pending_signals:
        if signal.confidence >= SIGNAL_CONFIDENCE_THRESHOLD:
            qualified.append(signal)
            continue
        # Count unique evidence sources (by fingerprint) with similar text
        sd = signal.signal_data if isinstance(signal.signal_data, dict) else {}
        sig_text = sd.get("text", "")
        sig_fp = sd.get("fingerprint", "")
        if not sig_text:
            continue
        sig_lower = sig_text.lower()
        # Collect unique fingerprints across all pending signals of same type
        seen_fps: set[str] = {sig_fp} if sig_fp else set()
        for other in pending_signals:
            if other.id == signal.id:
                continue
            if other.signal_type != signal.signal_type:
                continue
            od = other.signal_data if isinstance(other.signal_data, dict) else {}
            other_text = od.get("text", "")
            other_fp = od.get("fingerprint", "")
            if not other_text:
                continue
            if sig_lower in other_text.lower() or other_text.lower() in sig_lower:
                if other_fp and other_fp not in seen_fps:
                    seen_fps.add(other_fp)
        # Count unique evidence sources (≥ 2 different fingerprints ≈ repeated observation)
        if len(seen_fps) >= SIGNAL_REPEAT_THRESHOLD:
            qualified.append(signal)
    return qualified


async def _mark_signals_applied(db: AsyncSessionLocal, signals: list) -> None:
    """Mark signals as applied."""
    now = datetime.now(timezone.utc)
    for s in signals:
        s.applied = True
        s.applied_at = now
    await db.commit()


def _db_profile_to_dict(profile_data) -> dict:
    """Convert profile_data DB value to dict."""
    if isinstance(profile_data, dict):
        return profile_data
    if isinstance(profile_data, str):
        try:
            return json.loads(profile_data)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


async def _deduplicate_profile(profile: dict) -> dict:
    """Deduplicate semantically within each list field using LLM."""
    for key in ("taboos", "focus", "habits"):
        items = profile.get(key, [])
        if not isinstance(items, list) or len(items) <= 1:
            continue
        try:
            deduped = await _dedup_list(items)
            if deduped:
                profile[key] = deduped
        except Exception as e:
            logger.warning("Dedup failed for %s: %s", key, e)
    return profile


async def _dedup_list(items: list[str]) -> list[str]:
    """Use LLM to deduplicate semantically similar items."""
    if not items:
        return []
    text = json.dumps(items, ensure_ascii=False)
    messages = [
        {"role": "system", "content": MERGE_DETERMINISTIC_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    result = await gateway_router.chat(messages=messages, profile_key=MERGE_MODEL_KEY)
    content = result.get("content", "")
    if not content:
        return items
    try:
        parsed = _parse_json_array(content)
        if parsed and isinstance(parsed, list):
            return [str(x).strip() for x in parsed if x and str(x).strip()]
    except Exception:
        pass
    return items


def _parse_json_array(text: str) -> list | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        cleaned = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(cleaned).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return None


async def _apply_caps(profile: dict, pending_signals: list | None = None) -> dict:
    """Apply field caps, preferring high-confidence/recent/well-evidenced entries.

    Uses the following priority (higher = better):
    1. Number of supporting evidence fingerprints
    2. Signal confidence (max)
    3. Recency (newer = better, approximated by original order)

    This is NOT a simple ``items[:N]`` truncation — it scores each item
    and keeps the most- evidenced ones up to the cap.
    """
    caps = {"taboos": MAX_TABOOS, "focus": MAX_FOCUS, "habits": MAX_HABITS}

    # Build evidence score map from pending signals
    evidence_scores: dict[str, float] = {}
    if pending_signals:
        for sig in pending_signals:
            sd = sig.signal_data if isinstance(sig.signal_data, dict) else {}
            text = sd.get("text", "").strip().lower() if sd else ""
            fp = sd.get("fingerprint", "")
            if not text or not fp:
                continue
            current = evidence_scores.get(text, 0.0)
            evidence_scores[text] = current + 1.0 + (sig.confidence or 0.0) * 2.0

    for key, cap in caps.items():
        items = profile.get(key, [])
        if not isinstance(items, list) or len(items) <= cap:
            continue

        scored = []
        for idx, item in enumerate(items):
            item_lower = item.strip().lower() if isinstance(item, str) else str(item).strip().lower()
            ev_score = evidence_scores.get(item_lower, 1.0)
            # Recency bonus: later items (newer) get a small boost
            recency = idx / max(len(items), 1) * 0.5
            scored.append((ev_score + recency, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        profile[key] = [item for _, item in scored[:cap]]

    return profile


def _parse_profile_json(text: str) -> dict | None:
    """Attempt to extract JSON from LLM response text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            if line.strip().startswith("```"):
                continue
            cleaned.append(line)
        text = "\n".join(cleaned)
    text = text.strip()

    def _normalize(data: Any) -> dict | None:
        if not isinstance(data, dict):
            return None
        normalized: dict[str, Any] = {}
        tone = data.get("tone", "")
        normalized["tone"] = str(tone).strip() if tone is not None else ""
        for key in ("taboos", "focus", "habits"):
            value = data.get(key, [])
            if isinstance(value, str):
                value = [value] if value.strip() else []
            if not isinstance(value, list):
                value = []
            normalized[key] = [
                str(item).strip()
                for item in value
                if item is not None and str(item).strip()
            ]
        return normalized

    try:
        data = json.loads(text)
        normalized = _normalize(data)
        if normalized is not None:
            return normalized
    except json.JSONDecodeError:
        pass

    # Try extracting first JSON block
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            data = json.loads(candidate)
            normalized = _normalize(data)
            if normalized is not None:
                return normalized
        except json.JSONDecodeError:
            pass
        try:
            data = literal_eval(candidate)
            normalized = _normalize(data)
            if normalized is not None:
                return normalized
        except (SyntaxError, ValueError, TypeError):
            pass

    return None


async def _merge_profiles(old: dict, new: dict) -> dict:
    """Use LLM to merge old and new profiles, or fall back to simple merge."""
    # Simple merge strategy (fallback): new data overwrites old, lists merge uniquely
    merged = dict(old)

    for key in ("tone",):
        if key in new and new[key]:
            merged[key] = new[key]

    for key in ("taboos", "focus", "habits"):
        if key in new and isinstance(new[key], list) and new[key]:
            old_list = merged.get(key, [])
            if isinstance(old_list, list):
                # Union: keep old items not contradicted by new, add new items not in old
                old_set = set(item.strip().lower() for item in old_list if isinstance(item, str))
                for item in new[key]:
                    if isinstance(item, str) and item.strip().lower() not in old_set:
                        old_list.append(item.strip())
                        old_set.add(item.strip().lower())
                merged[key] = old_list
            else:
                merged[key] = new[key]

    return merged
