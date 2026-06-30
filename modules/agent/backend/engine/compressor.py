"""compressor：滑窗保头尾 + 中间摘要（便宜模型）。
与批1事件溯源对接：压缩 = 插入 compaction 事件，不删原始事件。
触发：budget_allocator装配时仍超预算 → 调compressor。
降级：便宜模型失败 → 退"只保尾部 M 条"硬截断，不报错。

批5增强：压缩前快照 + 压缩链路追踪 + 可回放审计。"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from .context_snapshot import take_snapshot
from .event_store import record_event

logger = logging.getLogger("v2.agent").getChild("engine.compressor")

HEAD_COUNT = 10
TAIL_COUNT = 20
MAX_SUMMARY_CHARS = 50000
MAX_COMPRESSION_ROUNDS = 5
COMPRESSION_RATIOS = [0, 10, 20, 50, 100]
CHEAP_MODEL_KEY = "gemma-4"

TOOL_EVENT_TYPES = {"tool_call", "tool_result"}
NON_FOLDABLE_TYPES = {"compaction", "memory_op", "system_event", "compression_trace"}
_ALREADY_FOLDED_IDS: set[int] = set()


def _reset_folded_ids() -> None:
    """Reset the in-memory folded-IDs set (for tests)."""
    _ALREADY_FOLDED_IDS.clear()


def _get_already_folded_ids(events: list) -> set[int]:
    """Collect IDs of events already folded in earlier compactions."""
    folded = set()
    for ev in events:
        etype = ev.event_type if hasattr(ev, "event_type") else ev.get("event_type", "")
        if etype != "compaction":
            continue
        payload = ev.payload if hasattr(ev, "payload") else ev.get("payload", {})
        if isinstance(payload, dict):
            for fid in (payload.get("folded_event_ids") or []):
                if fid:
                    folded.add(fid if isinstance(fid, int) else None)
    return folded


def _find_tool_pairs(events: list) -> list[tuple[int, int]]:
    """Pair tool_call events with their results using tool_call_id.

    The standard pairing key is the ``tool_call_id`` embedded in each
    event's payload.  Falls back to ``llm_response_id`` for legacy events
    that lack tool_call_id in the payload but share a response id.
    """
    pairs: list[tuple[int, int]] = []
    # Phase 1: collect tool_call_ids from tool_call events
    call_ids: dict[str, int] = {}  # tool_call_id → event index
    for idx, ev in enumerate(events):
        etype = ev.event_type if hasattr(ev, "event_type") else ev.get("event_type", "")
        if etype != "tool_call":
            continue
        payload = ev.payload if hasattr(ev, "payload") else ev.get("payload", {})
        if isinstance(payload, dict):
            tcid = payload.get("tool_call_id") or payload.get("id")
        else:
            tcid = None
        # Try tool_call_id from nested function call
        if not tcid:
            fn = payload.get("function", {}) if isinstance(payload, dict) else {}
            tcid = fn.get("tool_call_id") or fn.get("id")
        if tcid:
            call_ids[str(tcid)] = idx

    # Phase 2: match tool_result events to their tool_call via tool_call_id
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

    # Phase 3: fallback — pair by llm_response_id for events without tool_call_id
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
    import math
    return max(math.ceil(len(text) / 1.5), 0)


async def compress_middle_with_snapshot(
    db: "AsyncSession",
    conversation_id: int,
    all_events: list,
    messages: list[dict] | None = None,
    profile_key: str = CHEAP_MODEL_KEY,
) -> dict:
    """compress_middle with pre/post snapshots for replayability.

    Takes a snapshot before and after compression, linking them for audit.
    """
    # Pre-compress snapshot
    pre_snap = None
    if messages:
        pre_snap = await take_snapshot(
            db, conversation_id, "pre_compress",
            messages, all_events,
        )
    result = await compress_middle(db, conversation_id, all_events, profile_key)
    # Post-compress snapshot (re-read events for updated state)
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
            # Store compression_ratio on the snapshot for audit
            if snap and compression_ratio is not None:
                snap.compression_ratio = float(compression_ratio)
                snap.restored_from = pre_snap.id if pre_snap else None
                db.add(snap)
                await db.commit()

            # Record a compression_trace event linking pre/post snapshots
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
) -> dict:
    if len(all_events) <= HEAD_COUNT + TAIL_COUNT:
        return {"status": "skipped", "reason": "事件数不足，无需压缩"}

    # Collect IDs already folded in previous compactions
    previously_folded = _get_already_folded_ids(all_events)

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
        # Skip events already folded by a previous compaction
        ev_id = ev.id if hasattr(ev, "id") else ev.get("id")
        if ev_id and ev_id in previously_folded:
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
        compression_ratio = round(len(foldable_indices) / max(len(all_events), 1) * 100, 1)
        return {
            "status": "compressed",
            "compaction_id": ev.id,
            "folded_count": len(foldable_ids),
            "summary_preview": summary_text[:200],
            "compression_ratio": compression_ratio,
            "total_events_before": len(all_events),
        }
    except Exception as e:
        logger.error("记录 compaction 事件失败: %s", e)
        return {"status": "error", "error": str(e)}


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
