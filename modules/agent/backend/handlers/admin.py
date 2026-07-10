"""Admin endpoints for agent module.

Contains handler functions for:
  - GET /admin/replay/{conversation_id} — 事件重放
  - GET /admin/overview               — engine概览
  - GET /admin/snapshots/{conversation_id} — 快照列表与详情
  - GET /admin/snapshots/{snapshot_id}/restore — 快照恢复（只读审计）
  - GET /admin/approvals/pending       — 待确认对外操作列表
  - POST /admin/approvals/{id}/resolve — 授权决策
"""

from __future__ import annotations

import glob as _glob
import logging
from pathlib import Path

from app.core.exceptions import ValidationError
from app.schemas.common import ApiResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..engine.event_store import read_events
from ..services.action_policy import list_pending_approvals, resolve_approval

logger = logging.getLogger("v2.agent").getChild("handlers.admin")


async def handle_admin_replay(
    conversation_id: int, db: AsyncSession, user,
) -> ApiResponse:
    """事件重放：读取 agent_events，按轮次重建上下文装配过程。"""
    events = await read_events(db, conversation_id)
    if not events:
        return ApiResponse(data={"conversation_id": conversation_id, "rounds": [], "total_events": 0})

    rounds: list[dict] = []
    current_round: dict | None = None

    for ev in events:
        ev_dict = {
            "id": ev.id,
            "event_type": ev.event_type,
            "payload": ev.payload,
            "llm_response_id": ev.llm_response_id,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        }
        etype = ev.event_type

        if etype == "user_msg":
            if current_round:
                rounds.append(current_round)
            current_round = {
                "round_start_id": ev.id,
                "user_input": ev.payload.get("content", ""),
                "assembly_diag": None,
                "assistant_msg": None,
                "tool_calls": [],
                "tool_results": [],
                "compaction": None,
                "degradation": None,
                "events": [ev_dict],
            }
        elif etype == "assembly_diag" and current_round:
            current_round["assembly_diag"] = ev.payload
            current_round["events"].append(ev_dict)
        elif etype == "assistant_msg" and current_round:
            current_round["assistant_msg"] = ev.payload.get("content", "")
            current_round["events"].append(ev_dict)
        elif etype == "tool_call" and current_round:
            current_round["tool_calls"].append({
                "id": ev.payload.get("id", ""),
                "name": ev.payload.get("name", ""),
                "arguments": ev.payload.get("arguments", {}),
            })
            current_round["events"].append(ev_dict)
        elif etype == "tool_result" and current_round:
            current_round["tool_results"].append({
                "tool_call_id": ev.payload.get("tool_call_id", ""),
                "name": ev.payload.get("name", ""),
                "result": ev.payload.get("result", {}),
            })
            current_round["events"].append(ev_dict)
        elif etype == "compaction":
            if current_round:
                current_round["compaction"] = {
                    "folded_count": ev.payload.get("folded_count", 0),
                    "summary_preview": ev.payload.get("summary", "")[:300],
                    "compression_ratio": ev.payload.get("compression_ratio"),
                }
                current_round["events"].append(ev_dict)
            else:
                rounds.append({
                    "round_start_id": ev.id,
                    "user_input": "",
                    "assembly_diag": None,
                    "assistant_msg": None,
                    "tool_calls": [],
                    "tool_results": [],
                    "compaction": {
                        "folded_count": ev.payload.get("folded_count", 0),
                        "summary_preview": ev.payload.get("summary", "")[:300],
                        "compression_ratio": ev.payload.get("compression_ratio"),
                    },
                    "degradation": None,
                    "events": [ev_dict],
                })
                current_round = None
        elif etype == "compression_trace":
            if current_round:
                current_round["compression_trace"] = {
                    "pre_snapshot_id": ev.payload.get("pre_snapshot_id"),
                    "post_snapshot_id": ev.payload.get("post_snapshot_id"),
                    "compaction_event_id": ev.payload.get("compaction_event_id"),
                    "folded_count": ev.payload.get("folded_count", 0),
                    "compression_ratio": ev.payload.get("compression_ratio"),
                    "summary_preview": ev.payload.get("summary_preview", ""),
                }
                current_round["events"].append(ev_dict)
            else:
                rounds.append({
                    "round_start_id": ev.id,
                    "user_input": "",
                    "assembly_diag": None,
                    "assistant_msg": None,
                    "tool_calls": [],
                    "tool_results": [],
                    "compression_trace": {
                        "pre_snapshot_id": ev.payload.get("pre_snapshot_id"),
                        "post_snapshot_id": ev.payload.get("post_snapshot_id"),
                        "compaction_event_id": ev.payload.get("compaction_event_id"),
                        "folded_count": ev.payload.get("folded_count", 0),
                        "compression_ratio": ev.payload.get("compression_ratio"),
                    },
                    "degradation": None,
                    "events": [ev_dict],
                })
                current_round = None
        elif etype == "snapshot_restore":
            if current_round:
                current_round.setdefault("restore_events", []).append({
                    "snapshot_id": ev.payload.get("snapshot_id"),
                    "snapshot_type": ev.payload.get("snapshot_type"),
                    "event_id_before": ev.payload.get("event_id_before"),
                    "event_id_after": ev.payload.get("event_id_after"),
                })
                current_round["events"].append(ev_dict)
            else:
                rounds.append({
                    "round_start_id": ev.id,
                    "user_input": "",
                    "assembly_diag": None,
                    "assistant_msg": None,
                    "tool_calls": [],
                    "tool_results": [],
                    "restore_events": [{
                        "snapshot_id": ev.payload.get("snapshot_id"),
                        "snapshot_type": ev.payload.get("snapshot_type"),
                        "event_id_before": ev.payload.get("event_id_before"),
                        "event_id_after": ev.payload.get("event_id_after"),
                    }],
                    "degradation": None,
                    "events": [ev_dict],
                })
                current_round = None
        elif etype == "degradation" and current_round:
            current_round["degradation"] = {
                "from_profile": ev.payload.get("from", ""),
                "to_profile": ev.payload.get("to", ""),
                "reason": ev.payload.get("reason", ""),
            }
            current_round["events"].append(ev_dict)
        else:
            if current_round:
                current_round["events"].append(ev_dict)

    if current_round:
        rounds.append(current_round)

    return ApiResponse(data={
        "conversation_id": conversation_id,
        "rounds": rounds,
        "total_events": len(events),
    })


async def handle_admin_overview(db: AsyncSession, user) -> ApiResponse:
    """engine概览：记忆/经验/预算/压缩/降级/粘滞 各模块聚合统计。"""
    result: dict = {}

    # 1. 记忆 + 经验概览（跨模块走框架能力注册表，不直读 memory 的表）
    try:
        from app.services.module_registry import call_capability_as_system
        overview = await call_capability_as_system(
            "memory", "overview_stats", {},
            principal="system:agent-engine",
        )
        result["memory"] = overview.get("memory", {})
        result["experience"] = overview.get("experience", {})
    except Exception as e:
        logger.warning("Admin overview memory/experience query via capability failed: %s", e)
        result["memory"] = {"error": str(e)}
        result["experience"] = {"error": str(e)}

    # 3. 压缩概览
    try:
        comp_count = await db.scalar(text("SELECT COUNT(*) FROM agent_events WHERE event_type = 'compaction'"))
        comp_total_folded = await db.scalar(text(
            "SELECT COALESCE(SUM((payload->>'folded_count')::int), 0) FROM agent_events WHERE event_type = 'compaction'"
        ))
        hard_truncate = await db.scalar(text(
            "SELECT COUNT(*) FROM agent_events WHERE event_type = 'compaction' AND payload->>'fallback' = 'hard_truncate'"
        ))
        result["compression"] = {
            "compaction_count": comp_count or 0,
            "total_folded_events": comp_total_folded or 0,
            "hard_truncate_count": hard_truncate or 0,
        }
    except Exception as e:
        logger.warning("Admin overview compression query failed: %s", e)
        result["compression"] = {"error": str(e)}

    # 4. 降级概览
    try:
        deg_count = await db.scalar(text("SELECT COUNT(*) FROM agent_events WHERE event_type = 'degradation'"))
        result["degradation"] = {"degradation_count": deg_count or 0}
    except Exception as e:
        logger.warning("Admin overview degradation query failed: %s", e)
        result["degradation"] = {"error": str(e)}

    # 5. 对话统计
    try:
        conv_with_events = await db.scalar(text("SELECT COUNT(DISTINCT conversation_id) FROM agent_events"))
        total_events = await db.scalar(text("SELECT COUNT(*) FROM agent_events"))
        user_msg_count = await db.scalar(text("SELECT COUNT(*) FROM agent_events WHERE event_type = 'user_msg'"))
        tool_call_count = await db.scalar(text("SELECT COUNT(*) FROM agent_events WHERE event_type = 'tool_call'"))
        avg_events_per_conv = await db.scalar(text(
            "SELECT COALESCE(ROUND(AVG(cnt)), 0) FROM (SELECT COUNT(*) AS cnt FROM agent_events GROUP BY conversation_id) sub"
        ))
        result["conversations"] = {
            "conversation_count": conv_with_events or 0,
            "total_events": total_events or 0,
            "user_msg_count": user_msg_count or 0,
            "tool_call_count": tool_call_count or 0,
            "avg_events_per_conversation": avg_events_per_conv or 0,
        }
    except Exception as e:
        logger.warning("Admin overview conversation query failed: %s", e)
        result["conversations"] = {"error": str(e)}

    # 6. 粘滞统计
    try:
        stuck_count = 0
        log_dir = Path(__file__).resolve().parents[4] / "logs"
        if log_dir.exists():
            for log_file in _glob.glob(str(log_dir / "*.log")):
                try:
                    with open(log_file, "r", errors="ignore") as f:
                        for line in f:
                            if "stuck_detector命中" in line:
                                stuck_count += 1
                except Exception:
                    pass
        result["sticky"] = {"stuck_detection_count": stuck_count}
    except Exception as e:
        logger.warning("Admin overview sticky query failed: %s", e)
        result["sticky"] = {"error": str(e)}

    # 7. 成本概览
    try:
        total_today_cost = await db.scalar(text(
            "SELECT COALESCE(SUM(cost), 0) FROM agent_usage_daily WHERE usage_date = CURRENT_DATE"
        ))
        model_costs = await db.execute(text("""
            SELECT model_key, SUM(call_count) AS calls, SUM(prompt_tokens) AS prompt_tokens,
                   SUM(completion_tokens) AS completion_tokens, SUM(cost) AS cost
            FROM agent_usage_daily
            WHERE usage_date = CURRENT_DATE
            GROUP BY model_key ORDER BY cost DESC
        """))
        module_calls = await db.execute(text("""
            SELECT module, SUM(call_count) AS calls, SUM(cost) AS cost
            FROM agent_usage_daily
            WHERE usage_date = CURRENT_DATE
            GROUP BY module ORDER BY cost DESC
        """))
        last_7_days = await db.execute(text("""
            SELECT usage_date, SUM(cost) AS cost
            FROM agent_usage_daily
            WHERE usage_date >= CURRENT_DATE - 7
            GROUP BY usage_date ORDER BY usage_date
        """))
        result["cost"] = {
            "today_total": round(float(total_today_cost or 0), 4),
            "by_model": [
                {"model_key": r[0], "calls": r[1], "prompt_tokens": r[2], "completion_tokens": r[3], "cost": round(float(r[4] or 0), 4)}
                for r in model_costs.fetchall()
            ],
            "by_module": [
                {"module": r[0], "calls": r[1], "cost": round(float(r[2] or 0), 4)}
                for r in module_calls.fetchall()
            ],
            "last_7_days": [
                {"date": str(r[0]), "cost": round(float(r[1] or 0), 4)}
                for r in last_7_days.fetchall()
            ],
        }
    except Exception as e:
        logger.warning("Admin overview cost query failed: %s", e)
        result["cost"] = {"error": str(e)}

    return ApiResponse(data=result)


async def handle_admin_hook_lifecycle(db: AsyncSession, user) -> ApiResponse:
    """Hook 生命周期状态：维护循环状态、hook 运行历史。"""
    from ..engine.post_turn_hooks import get_hook_lifecycle_state
    state = get_hook_lifecycle_state()
    return ApiResponse(data=state)


async def handle_admin_memory_quality(db: AsyncSession, user) -> ApiResponse:
    """记忆检索质量概览：命中率、噪声率、可信度得分（engine 侧治理指标）。"""
    from ..engine.layered_memory import get_recall_quality_summary
    quality = get_recall_quality_summary()
    return ApiResponse(data=quality)


async def handle_admin_compression_chain(
    conversation_id: int, db: AsyncSession, user,
) -> ApiResponse:
    """压缩链审计：追踪 conversation 的压缩事件、快照和恢复溯源。

    返回时间排序的链，每条链节包含：
      - 如果是 compaction 事件: folded_count, summary_preview, compression_ratio
      - 关联的 pre_snapshot 和 post_snapshot
      - 如果有 restore 事件: restored_from snapshot_id
    """
    from ..engine.context_snapshot import list_snapshots
    from ..engine.event_store import read_events

    events = await read_events(db, conversation_id)
    snapshots = await list_snapshots(db, conversation_id, limit=50)

    # Build snapshot lookup
    snap_map: dict[int, dict] = {}
    for snap in snapshots:
        snap_map[snap.id] = {
            "id": snap.id,
            "snapshot_type": snap.snapshot_type,
            "event_id_before": snap.event_id_before,
            "event_id_after": snap.event_id_after,
            "compression_ratio": snap.compression_ratio,
            "restored_from": snap.restored_from,
            "summary": snap.summary,
            "created_at": snap.created_at.isoformat() if snap.created_at else None,
        }

    chain: list[dict] = []
    for ev in events:
        etype = ev.event_type
        if etype == "compaction":
            chain.append({
                "event_type": "compaction",
                "event_id": ev.id,
                "folded_count": ev.payload.get("folded_count", 0),
                "summary_preview": (ev.payload.get("summary", "") or "")[:300],
                "compression_ratio": ev.payload.get("compression_ratio"),
                "total_events_before": ev.payload.get("total_events_before"),
                "fallback": ev.payload.get("fallback"),
                "timestamp": ev.created_at.isoformat() if ev.created_at else None,
            })
        elif etype == "compression_trace":
            pre_id = ev.payload.get("pre_snapshot_id")
            post_id = ev.payload.get("post_snapshot_id")
            chain.append({
                "event_type": "compression_trace",
                "event_id": ev.id,
                "folded_count": ev.payload.get("folded_count", 0),
                "compression_ratio": ev.payload.get("compression_ratio"),
                "summary_preview": ev.payload.get("summary_preview", ""),
                "pre_snapshot": snap_map.get(pre_id) if pre_id else None,
                "post_snapshot": snap_map.get(post_id) if post_id else None,
                "timestamp": ev.created_at.isoformat() if ev.created_at else None,
            })
        elif etype == "snapshot_restore":
            snap_id = ev.payload.get("snapshot_id")
            chain.append({
                "event_type": "snapshot_restore",
                "event_id": ev.id,
                "snapshot_id": snap_id,
                "snapshot_type": ev.payload.get("snapshot_type"),
                "restored_snapshot": snap_map.get(snap_id) if snap_id else None,
                "timestamp": ev.created_at.isoformat() if ev.created_at else None,
            })

    return ApiResponse(data={
        "conversation_id": conversation_id,
        "total_snapshots": len(snapshots),
        "total_events": len(events),
        "chain": chain,
    })


async def handle_list_approvals(db: AsyncSession, user) -> ApiResponse:
    """列出所有待确认的对外操作请求。"""
    items = await list_pending_approvals(db)
    return ApiResponse(data=items)


async def handle_resolve_approval(
    approval_id: int, decision: str, reason: str | None,
    db: AsyncSession, user, payload_hash: str | None = None,
) -> ApiResponse:
    """授权（同意/拒绝）一个等待确认的对外操作。"""
    if decision not in ("approved", "rejected"):
        raise ValidationError("decision must be 'approved' or 'rejected'")
    result = await resolve_approval(db, approval_id, decision, user.id, reason, payload_hash)
    return ApiResponse(data=result)


async def handle_admin_snapshots(
    conversation_id: int, db: AsyncSession, user,
) -> ApiResponse:
    """快照列表：返回 conversation 所有快照的管理展示字段。"""
    from ..engine.context_snapshot import count_snapshots, list_snapshots

    snapshots = await list_snapshots(db, conversation_id, limit=50)
    total = await count_snapshots(db, conversation_id)

    items = []
    for snap in snapshots:
        items.append({
            "id": snap.id,
            "snapshot_type": snap.snapshot_type,
            "event_id_before": snap.event_id_before,
            "event_id_after": snap.event_id_after,
            "message_count_before": snap.message_count_before,
            "message_count_after": snap.message_count_after,
            "token_estimate_before": snap.token_estimate_before,
            "token_estimate_after": snap.token_estimate_after,
            "compression_ratio": snap.compression_ratio,
            "restored_from": snap.restored_from,
            "summary": snap.summary,
            "created_at": snap.created_at.isoformat() if snap.created_at else None,
        })

    return ApiResponse(data={
        "conversation_id": conversation_id,
        "total_snapshots": total,
        "snapshots": items,
    })


async def handle_admin_snapshot_restore(
    snapshot_id: int, db: AsyncSession, user,
) -> ApiResponse:
    """快照恢复（append-only 审计）：恢复指定快照并记录 restore 事件。

    该操作会追加一条 `snapshot_restore` 审计事件，但不回写原始
    conversation 消息流。恢复结果仅用于查看和审计。
    """
    from ..engine.context_snapshot import restore_snapshot

    messages = await restore_snapshot(db, snapshot_id)
    from sqlalchemy import select

    from ..models import ContextSnapshot
    r = await db.execute(select(ContextSnapshot).where(ContextSnapshot.id == snapshot_id))
    snap = r.scalar_one_or_none()

    return ApiResponse(data={
        "snapshot_id": snapshot_id,
        "restored_messages": len(messages),
        "snapshot_type": snap.snapshot_type if snap else None,
        "compression_ratio": snap.compression_ratio if snap else None,
        "event_id_before": snap.event_id_before if snap else None,
        "event_id_after": snap.event_id_after if snap else None,
        "summary": snap.summary if snap else None,
        "messages": messages,
    })
