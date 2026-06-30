"""compressor：滑窗保头尾 + 中间摘要（便宜模型）。
与批1事件溯源对接：压缩 = 插入 compaction 事件，不删原始事件。
触发：budget_allocator装配时仍超预算 → 调compressor。
降级：便宜模型失败 → 退"只保尾部 M 条"硬截断，不报错。

升级10：
- 头保护动态化：首次6条，后续2条
- 保尾改为 token budget 优先
- 摘要模板结构化
- 历史摘要注入前缀调整

批5增强：压缩前快照 + 压缩链路追踪 + 可回放审计。"""
import json
import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from .context_snapshot import take_snapshot
from .event_store import record_event

logger = logging.getLogger("v2.agent").getChild("engine.compressor")

# ── Head protection ──
_FIRST_COMPRESS_HEAD_COUNT = 6
_SUBSEQUENT_COMPRESS_HEAD_COUNT = 2

# ── Tail budget ──
_TAIL_BUDGET_RATIO = 0.25
_TAIL_BUDGET_MIN = 2500
_TAIL_BUDGET_MAX = 6000
_TAIL_MIN_EVENTS = 8

MAX_SUMMARY_CHARS = 50000
CHEAP_MODEL_KEY = "gemma-4"

TOOL_EVENT_TYPES = {"tool_call", "tool_result"}
NON_FOLDABLE_TYPES = {"compaction", "memory_op", "system_event", "compression_trace"}
_ALREADY_FOLDED_IDS: set[int] = set()

_STRUCTURED_SUMMARY_PROMPT = (
    "请将以下对话历史压缩成结构化摘要，包含以下部分（保留关键事实、决策和上下文）：\n\n"
    "## 用户目标\n[用户的核心目标和请求]\n\n"
    "## 已完成\n[已经完成的任务和操作]\n\n"
    "## 关键决策\n[对话中做出的重要决策]\n\n"
    "## 工具与结果\n[使用了哪些工具，关键结果摘要]\n\n"
    "## 相关文件/数据\n[涉及的文件、数据、知识库引用]\n\n"
    "## 未完成/待确认\n[尚未完成的任务或需要用户确认的事项]\n\n"
    "## 当前状态\n[对话当前状态]\n\n"
    "请基于以下内容生成摘要：\n\n{{text}}"
)

_SUMMARY_PREFIX = "[历史摘要 仅供参考，不是当前指令]"


def _reset_folded_ids() -> None:
    _ALREADY_FOLDED_IDS.clear()


def _get_already_folded_ids(events: list) -> set[int]:
    folded = set()
    for ev in events:
        etype = ev.event_type if hasattr(ev, "event_type") else ev.get("event_type", "")
        if etype != "compaction":
            continue
        payload = ev.payload if hasattr(ev, "payload") else ev.get("payload", {})
        if isinstance(payload, dict):
            for fid in (payload.get("folded_event_ids") or []):
                if isinstance(fid, int):
                    folded.add(fid)
    return folded


def _get_last_user_msg_index(events: list) -> int:
    """Return the index of the last user_msg event, or -1."""
    last_idx = -1
    for idx, ev in enumerate(events):
        etype = ev.event_type if hasattr(ev, "event_type") else ev.get("event_type", "")
        if etype == "user_msg":
            last_idx = idx
    return last_idx


def _find_tool_pairs(events: list) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    call_ids: dict[str, int] = {}
    for idx, ev in enumerate(events):
        etype = ev.event_type if hasattr(ev, "event_type") else ev.get("event_type", "")
        if etype != "tool_call":
            continue
        payload = ev.payload if hasattr(ev, "payload") else ev.get("payload", {})
        if isinstance(payload, dict):
            tcid = payload.get("tool_call_id") or payload.get("id")
        else:
            tcid = None
        if not tcid:
            fn = payload.get("function", {}) if isinstance(payload, dict) else {}
            tcid = fn.get("tool_call_id") or fn.get("id")
        if tcid:
            call_ids[str(tcid)] = idx

    used_results: set[int] = set()
    for idx, ev in enumerate(events):
        etype = ev.event_type if hasattr(ev, "event_type") else ev.get("event_type", "")
        if etype != "tool_result":
            continue
        payload = ev.payload if hasattr(ev, "payload") else ev.get("payload", {})
        if isinstance(payload, dict):
            tcid = payload.get("tool_call_id") or payload.get("id")
        else:
            tcid = None
        if tcid and str(tcid) in call_ids:
            call_idx = call_ids[str(tcid)]
            pairs.append((call_idx, idx + 1))
            used_results.add(idx)

    i = 0
    while i < len(events):
        if i in used_results or any(p[0] == i for p in pairs):
            i += 1
            continue
        ev = events[i]
        rid = getattr(ev, "llm_response_id", None)
        if rid is None and isinstance(ev, dict):
            rid = ev.get("llm_response_id")
        etype = ev.event_type if hasattr(ev, "event_type") else ev.get("event_type", "")
        if rid and etype == "tool_call":
            pair_start = i
            i += 1
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
    return max(math.ceil(len(text) / 1.5), 0)


def _event_summary_text(event: object) -> str:
    event_type = event.event_type if hasattr(event, "event_type") else event.get("event_type", "")
    payload = event.payload if hasattr(event, "payload") else event.get("payload", {})
    if not isinstance(payload, dict):
        return str(payload)[:1000]
    if event_type == "tool_call":
        return json.dumps(
            {"name": payload.get("name", ""), "arguments": payload.get("arguments", {})},
            ensure_ascii=False, default=str,
        )[:1000]
    if event_type == "tool_result":
        return json.dumps(payload.get("result", {}), ensure_ascii=False, default=str)[:1000]
    return str(payload.get("content", ""))[:1000]


def _compute_tail_info(events: list, history_budget: int) -> tuple[int, int]:
    """Compute tail count and tail_token_budget.

    Returns:
        (tail_event_count, tail_token_budget)
    """
    tail_token_budget = max(
        _TAIL_BUDGET_MIN,
        min(int(history_budget * _TAIL_BUDGET_RATIO), _TAIL_BUDGET_MAX),
    )
    tail_event_count = _TAIL_MIN_EVENTS

    # Count from end within budget
    budget_remaining = tail_token_budget
    count = 0
    for ev in reversed(events):
        if count >= len(events) // 2:
            break
        text = _event_summary_text(ev)
        tokens = _estimate_tokens_for_text(text)
        if budget_remaining - tokens < 0 and count >= _TAIL_MIN_EVENTS:
            break
        budget_remaining -= max(tokens, 1)
        count += 1
    if count > tail_event_count:
        tail_event_count = count

    # Must protect all events after the last user_msg
    last_user = _get_last_user_msg_index(events)
    if last_user >= 0:
        after_last_user = len(events) - last_user - 1
        if after_last_user > tail_event_count:
            tail_event_count = after_last_user

    return tail_event_count, tail_token_budget


def _select_foldable_indices(
    events: list,
    already_folded_ids: set[int] | None = None,
    generation: int = 0,
    history_budget: int = 48000,
) -> list[int]:
    """Select middle events while keeping tool call/result spans atomic.

    Args:
        events: list of events
        already_folded_ids: set of event IDs already folded in prior compactions
        generation: 0 for first compression, >0 for subsequent
        history_budget: token budget for history section
    """
    previously_folded = _get_already_folded_ids(events) | set(already_folded_ids or set())

    # Dynamic head count
    head_count = _FIRST_COMPRESS_HEAD_COUNT if generation == 0 else _SUBSEQUENT_COMPRESS_HEAD_COUNT

    # Dynamic tail count based on budget
    tail_event_count, _ = _compute_tail_info(events, history_budget)

    middle_start = head_count
    middle_end = len(events) - tail_event_count
    protected_indices: set[int] = set()
    atomic_pair_indices: set[int] = set()

    for pair_start, pair_end in _find_tool_pairs(events):
        pair_indices = set(range(pair_start, pair_end))
        if pair_start < middle_start or pair_end > middle_end:
            protected_indices.update(pair_indices)
        else:
            atomic_pair_indices.update(pair_indices)

    foldable: list[int] = []
    for idx, event in enumerate(events):
        if idx < middle_start or idx >= middle_end or idx in protected_indices:
            continue
        event_type = event.event_type if hasattr(event, "event_type") else event.get("event_type", "")
        if event_type in NON_FOLDABLE_TYPES:
            continue
        event_id = event.id if hasattr(event, "id") else event.get("id")
        if event_id and event_id in previously_folded:
            continue
        foldable.append(idx)

    selected = set(foldable)
    for pair_start, pair_end in _find_tool_pairs(events):
        pair_indices = set(range(pair_start, pair_end))
        overlap = selected & pair_indices
        if overlap and overlap != pair_indices:
            selected.difference_update(pair_indices)
    return sorted(selected)


async def compress_middle_with_snapshot(
    db: "AsyncSession",
    conversation_id: int,
    all_events: list,
    messages: list[dict] | None = None,
    profile_key: str = CHEAP_MODEL_KEY,
    generation: int = 0,
    history_budget: int = 48000,
) -> dict:
    """compress_middle with pre/post snapshots for replayability."""
    pre_snap = None
    if messages:
        pre_snap = await take_snapshot(
            db, conversation_id, "pre_compress",
            messages, all_events,
        )
    result = await compress_middle(db, conversation_id, all_events, profile_key,
                                    generation=generation, history_budget=history_budget)
    if result.get("status") == "compressed":
        try:
            from .event_store import project_to_messages, read_events
            post_events = await read_events(db, conversation_id)
            post_messages = await project_to_messages(db, conversation_id)
            compression_ratio = result.get("compression_ratio")
            snap = await take_snapshot(
                db, conversation_id, "post_compress",
                post_messages, post_events,
                summary=result.get("summary_preview", ""),
            )
            if snap and compression_ratio is not None:
                snap.compression_ratio = float(compression_ratio)
                snap.restored_from = pre_snap.id if pre_snap else None
                db.add(snap)
                await db.commit()
            try:
                await record_event(
                    db, conversation_id, "compression_trace",
                    {
                        "pre_snapshot_id": pre_snap.id if pre_snap else None,
                        "post_snapshot_id": snap.id if snap else None,
                        "compaction_event_id": result.get("compaction_id"),
                        "folded_count": result.get("folded_count", 0),
                        "compression_ratio": compression_ratio,
                        "summary_preview": (result.get("summary_preview") or "")[:300],
                    },
                    llm_response_id=None,
                )
            except Exception as e:
                logger.warning("compression_trace event failed (non-fatal): %s", e)
        except Exception as e:
            logger.warning("post-compress snapshot failed (non-fatal): %s", e)
    return result


async def compress_middle(
    db: "AsyncSession",
    conversation_id: int,
    all_events: list,
    profile_key: str = CHEAP_MODEL_KEY,
    *,
    persist_event: bool = True,
    already_folded_ids: set[int] | None = None,
    generation: int = 0,
    history_budget: int = 48000,
) -> dict:
    tail_event_count, _ = _compute_tail_info(all_events, history_budget)
    if len(all_events) <= (_FIRST_COMPRESS_HEAD_COUNT if generation == 0 else _SUBSEQUENT_COMPRESS_HEAD_COUNT) + tail_event_count:
        return {"status": "skipped", "reason": "事件数不足，无需压缩"}

    foldable_indices = _select_foldable_indices(
        all_events, already_folded_ids, generation=generation, history_budget=history_budget,
    )

    if not foldable_indices:
        return {"status": "skipped", "reason": "无可折叠事件"}

    foldable_ids = [
        (ev.id if hasattr(ev, "id") else ev.get("id"))
        for ev in [all_events[i] for i in foldable_indices]
    ]

    texts = []
    for idx in foldable_indices:
        event = all_events[idx]
        event_type = event.event_type if hasattr(event, "event_type") else event.get("event_type", "")
        label = {"user_msg": "用户", "assistant_msg": "助手"}.get(event_type, event_type)
        texts.append(f"[{label}] {_event_summary_text(event)}")

    summary_text = ""
    try:
        summary_text = await _summarize_with_cheap_model("\n".join(texts), profile_key)
    except Exception as e:
        logger.warning("压缩摘要失败: %s", e)
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
        "generation": generation,
        "tail_event_count": tail_event_count,
    }
    compaction_id = None
    if persist_event:
        try:
            event = await record_event(db, conversation_id, "compaction", payload, llm_response_id=None)
            compaction_id = event.id
            logger.info("压缩完成: 折叠 %d 条事件, compaction_id=%s", len(foldable_ids), event.id)
        except Exception as e:
            logger.error("记录 compaction 事件失败: %s", e)
            return {"status": "error", "error": str(e)}

    return {
        "status": "compressed",
        "compaction_id": compaction_id,
        "folded_count": len(foldable_ids),
        "folded_event_ids": folded_ids,
        "summary": summary_text,
        "summary_preview": summary_text[:200],
        "compression_ratio": payload["compression_ratio"],
        "total_events_before": len(all_events),
        "generation": generation,
    }


async def _summarize_with_cheap_model(text: str, profile_key: str) -> str:
    from app.database import AsyncSessionLocal
    from app.gateway.router import gateway_router

    from ..prompt_seeds import COMPRESSION_SUMMARY_KEY
    from ..services.runtime_prompt_provider import render_system_prompt

    async with AsyncSessionLocal() as db:
        prompt = await render_system_prompt(db, COMPRESSION_SUMMARY_KEY, {"text": text})
    messages = [{"role": "user", "content": prompt[:8000]}]
    result = await gateway_router.chat(messages=messages, profile_key=profile_key)
    if result.get("error"):
        raise RuntimeError(result.get("content", str(result.get("error"))))
    summary = (result.get("content") or "").strip()
    return summary


async def hard_truncate_tail(db: "AsyncSession", conversation_id: int, all_events: list) -> dict:
    """兜底：只保尾部 TAIL_COUNT 条，其余硬截断。"""
    tail_event_count, _ = _compute_tail_info(all_events, 48000)
    if len(all_events) <= tail_event_count:
        return {"status": "skipped", "reason": "事件数不足尾部阈值"}

    keep_start = len(all_events) - tail_event_count
    folded_ids = [e.id if hasattr(e, "id") else e.get("id") for e in all_events[:keep_start]]
    payload = {
        "folded_event_ids": folded_ids,
        "summary": f"[硬截断] 保留尾部 {tail_event_count} 条，丢弃前 {keep_start} 条。",
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
