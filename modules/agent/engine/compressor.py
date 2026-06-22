"""压缩器：滑窗保头尾 + 中间摘要（便宜模型）。
与批1事件溯源对接：压缩 = 插入 compaction 事件，不删原始事件。
触发：预算分配器装配时仍超预算 → 调压缩器。
降级：便宜模型失败 → 退"只保尾部 M 条"硬截断，不报错。"""
import json
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from 事件存储 import record_event

logger = logging.getLogger("v2.agent.engine.压缩器")

HEAD_COUNT = 10
TAIL_COUNT = 20
MAX_SUMMARY_CHARS = 50000
MAX_COMPRESSION_ROUNDS = 5
COMPRESSION_RATIOS = [0, 10, 20, 50, 100]
CHEAP_MODEL_KEY = "gemma-4"

TOOL_EVENT_TYPES = {"tool_call", "tool_result"}
NON_FOLDABLE_TYPES = {"compaction", "memory_op", "system_event"}


def _find_tool_pairs(events: list) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    i = 0
    while i < len(events):
        ev = events[i]
        rid = getattr(ev, "llm_response_id", None)
        if rid is None and isinstance(ev, dict):
            rid = ev.get("llm_response_id")
        etype = ev.event_type if hasattr(ev, "event_type") else ev.get("event_type", "")
        if rid and etype == "tool_call":
            pair_start = i
            while i < len(events):
                ev2 = events[i]
                rid2 = getattr(ev2, "llm_response_id", None)
                if rid2 is None and isinstance(ev2, dict):
                    rid2 = ev2.get("llm_response_id")
                etype2 = ev2.event_type if hasattr(ev2, "event_type") else ev2.get("event_type", "")
                if rid2 != rid or (etype2 not in TOOL_EVENT_TYPES):
                    break
                i += 1
            pairs.append((pair_start, i))
        else:
            i += 1
    return pairs


def _estimate_tokens_for_text(text: str) -> int:
    import math
    return max(math.ceil(len(text) / 1.5), 0)


async def 压缩中间(
    db: "AsyncSession",
    conversation_id: int,
    all_events: list,
    profile_key: str = CHEAP_MODEL_KEY,
) -> dict:
    if len(all_events) <= HEAD_COUNT + TAIL_COUNT:
        return {"status": "skipped", "reason": "事件数不足，无需压缩"}

    tool_pairs = _find_tool_pairs(all_events)

    freezable = set()
    for pair_start, pair_end in tool_pairs:
        for idx in range(pair_start, pair_end):
            freezable.add(idx)

    foldable_indices: list[int] = []
    for idx, ev in enumerate(all_events):
        etype = ev.event_type if hasattr(ev, "event_type") else ev.get("event_type", "")
        if etype in NON_FOLDABLE_TYPES:
            continue
        if idx in freezable:
            continue
        if idx < HEAD_COUNT or idx >= len(all_events) - TAIL_COUNT:
            continue
        foldable_indices.append(idx)

    if not foldable_indices:
        return {"status": "skipped", "reason": "无可折叠事件"}

    foldable_ids = [
        (ev.id if hasattr(ev, "id") else ev.get("id"))
        for ev in [all_events[i] for i in foldable_indices]
    ]

    summary_text = ""

    for round_idx in range(MAX_COMPRESSION_ROUNDS):
        ratio = COMPRESSION_RATIOS[round_idx] if round_idx < len(COMPRESSION_RATIOS) else 100
        if ratio == 0:
            continue
        sample_count = max(1, len(foldable_indices) * ratio // 100)
        sample_events = [all_events[i] for i in foldable_indices[:sample_count]]

        texts = []
        for ev in sample_events:
            etype = ev.event_type if hasattr(ev, "event_type") else ev.get("event_type", "")
            payload = ev.payload if hasattr(ev, "payload") else ev.get("payload", {})
            content = payload.get("content", "") if isinstance(payload, dict) else str(payload)
            label = {"user_msg": "用户", "assistant_msg": "助手"}.get(etype, etype)
            texts.append(f"[{label}] {str(content)[:500]}")
        combined = "\n".join(texts)

        try:
            summary_text = await _summarize_with_cheap_model(combined, profile_key)
            if summary_text and len(summary_text) < MAX_SUMMARY_CHARS:
                break
        except Exception as e:
            logger.warning("压缩第 %d 轮失败: %s", round_idx + 1, e)
            if round_idx == 0:
                summary_text = ""
    if not summary_text:
        summary_text = f"[压缩摘要] 共折叠 {len(foldable_ids)} 条中间事件，压缩失败，降级为硬截断。"

    folded_ids = [e.id if hasattr(e, "id") else e.get("id") for e in [all_events[i] for i in foldable_indices]]
    summary_text = summary_text[:MAX_SUMMARY_CHARS]

    payload = {
        "folded_event_ids": folded_ids,
        "summary": summary_text,
        "compression_ratio": round(len(foldable_indices) / max(len(all_events), 1) * 100, 1),
        "folded_count": len(foldable_indices),
        "total_events_before": len(all_events),
    }
    try:
        ev = await record_event(db, conversation_id, "compaction", payload, llm_response_id=None)
        logger.info("压缩完成: 折叠 %d 条事件, compaction_id=%s", len(foldable_ids), ev.id)
        return {"status": "compressed", "compaction_id": ev.id, "folded_count": len(foldable_ids), "summary_preview": summary_text[:200]}
    except Exception as e:
        logger.error("记录 compaction 事件失败: %s", e)
        return {"status": "error", "error": str(e)}


async def _summarize_with_cheap_model(text: str, profile_key: str) -> str:
    from app.gateway.router import gateway_router
    prompt = (
        "请将以下对话历史压缩成一段连贯的摘要，保留关键事实、决策和上下文。"
        "输出纯文本摘要，不要额外格式。\n\n"
        f"{text}"
    )
    messages = [{"role": "user", "content": prompt[:8000]}]
    result = await gateway_router.chat(messages=messages, profile_key=profile_key)
    if result.get("error"):
        raise RuntimeError(result.get("content", str(result.get("error"))))
    summary = (result.get("content") or "").strip()
    return summary


async def 硬截断尾部(db: "AsyncSession", conversation_id: int, all_events: list) -> dict:
    """兜底：只保尾部 TAIL_COUNT 条，其余硬截断。"""
    if len(all_events) <= TAIL_COUNT:
        return {"status": "skipped", "reason": "事件数不足尾部阈值"}

    keep_start = len(all_events) - TAIL_COUNT
    folded_ids = [e.id if hasattr(e, "id") else e.get("id") for e in all_events[:keep_start]]
    payload = {
        "folded_event_ids": folded_ids,
        "summary": f"[硬截断] 保留尾部 {TAIL_COUNT} 条，丢弃前 {keep_start} 条。",
        "compression_ratio": round(keep_start / max(len(all_events), 1) * 100, 1),
        "folded_count": len(folded_ids),
        "total_events_before": len(all_events),
        "fallback": "hard_truncate",
    }
    try:
        ev = await record_event(db, conversation_id, "compaction", payload, llm_response_id=None)
        return {"status": "compressed", "compaction_id": ev.id, "folded_count": len(folded_ids), "fallback": True}
    except Exception as e:
        return {"status": "error", "error": str(e)}
