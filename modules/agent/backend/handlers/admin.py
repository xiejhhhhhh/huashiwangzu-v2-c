"""Admin endpoints for agent module.

Contains handler functions for:
  - GET /admin/replay/{conversation_id} — 事件重放
  - GET /admin/overview               — engine概览
  - GET /admin/approvals/pending       — 待审批列表
  - POST /admin/approvals/{id}/resolve — 审批决策
"""

from __future__ import annotations

import glob as _glob
import json
import logging
from pathlib import Path

from sqlalchemy import text, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.schemas.common import ApiResponse

from ..engine.event_store import read_events
from ..action_policy import resolve_approval, list_pending_approvals

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
        from app.services.module_registry import call_capability
        overview = await call_capability(
            "memory", "overview_stats", {},
            caller="system:agent-engine",
            caller_role="admin",
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
        log_dir = Path(__file__).resolve().parent.parent.parent.parent / "backend" / "logs"
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


async def handle_list_approvals(db: AsyncSession, user) -> ApiResponse:
    """列出所有待审批的敏感操作请求。"""
    items = await list_pending_approvals(db)
    return ApiResponse(data=items)


async def handle_resolve_approval(
    approval_id: int, decision: str, reason: str | None,
    db: AsyncSession, user,
) -> ApiResponse:
    """审批（同意/拒绝）一个等待确认的敏感操作。"""
    if decision not in ("approved", "rejected"):
        raise ValidationError("decision must be 'approved' or 'rejected'")
    result = await resolve_approval(db, approval_id, decision, user.id, reason)
    return ApiResponse(data=result)
