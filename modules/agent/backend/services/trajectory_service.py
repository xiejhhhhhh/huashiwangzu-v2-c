"""Lightweight trajectory recording for research and analysis.

Records user input, tool calls, results, corrections, failure recovery,
thinking levels, and profile signals per turn. Data is used for
research, trajectory compression, and tool selection optimization,
not for real-time decisions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentTrajectoryRecord

logger = logging.getLogger("v2.agent").getChild("services.trajectory_service")


async def record_turn(
    db: AsyncSession,
    conversation_id: int,
    owner_id: int,
    session_id: str,
    turn_index: int,
    user_input: str,
    tool_calls: list | None = None,
    tool_results: list | None = None,
    assistant_response: str | None = None,
    user_correction: str | None = None,
    failure_recovery: dict | None = None,
    thinking_level: str | None = None,
    profile_signals: list | None = None,
    error_occurred: bool = False,
    duration_ms: float | None = None,
    token_count: int | None = None,
) -> dict:
    """Record a single turn trajectory entry."""
    try:
        record = AgentTrajectoryRecord(
            conversation_id=conversation_id,
            owner_id=owner_id,
            session_id=session_id,
            turn_index=turn_index,
            user_input=user_input[:2000],
            tool_calls=tool_calls or [],
            tool_results=tool_results or [],
            assistant_response=assistant_response[:5000] if assistant_response else None,
            user_correction=user_correction,
            failure_recovery=failure_recovery,
            thinking_level=thinking_level,
            profile_signals=profile_signals or [],
            error_occurred=error_occurred,
            duration_ms=duration_ms,
            token_count=token_count,
        )
        db.add(record)
        await db.commit()
        return {"id": record.id, "turn_index": turn_index, "recorded": True}
    except Exception as e:
        logger.warning("Failed to record trajectory turn: %s", e)
        return {"error": str(e), "recorded": False}


async def list_trajectories(
    db: AsyncSession,
    owner_id: int | None = None,
    conversation_id: int | None = None,
    session_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List trajectory records with optional filters."""
    q = select(AgentTrajectoryRecord).order_by(desc(AgentTrajectoryRecord.created_at)).limit(limit)
    if owner_id is not None:
        q = q.where(AgentTrajectoryRecord.owner_id == owner_id)
    if conversation_id is not None:
        q = q.where(AgentTrajectoryRecord.conversation_id == conversation_id)
    if session_id:
        q = q.where(AgentTrajectoryRecord.session_id == session_id)
    r = await db.execute(q)
    return [
        {
            "id": t.id,
            "conversation_id": t.conversation_id,
            "owner_id": t.owner_id,
            "session_id": t.session_id,
            "turn_index": t.turn_index,
            "user_input": t.user_input[:500] if t.user_input else "",
            "tool_call_count": len(t.tool_calls or []),
            "tool_result_count": len(t.tool_results or []),
            "assistant_response_preview": (t.assistant_response or "")[:200],
            "user_correction": t.user_correction,
            "failure_recovery": t.failure_recovery,
            "thinking_level": t.thinking_level,
            "error_occurred": t.error_occurred,
            "duration_ms": t.duration_ms,
            "token_count": t.token_count,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in r.scalars().all()
    ]


async def get_trajectory_detail(db: AsyncSession, trajectory_id: int) -> dict | None:
    """Get full detail of a single trajectory record."""
    r = await db.execute(
        select(AgentTrajectoryRecord).where(AgentTrajectoryRecord.id == trajectory_id)
    )
    t = r.scalar_one_or_none()
    if not t:
        return None
    return {
        "id": t.id,
        "conversation_id": t.conversation_id,
        "owner_id": t.owner_id,
        "session_id": t.session_id,
        "turn_index": t.turn_index,
        "user_input": t.user_input,
        "tool_calls": t.tool_calls,
        "tool_results": t.tool_results,
        "assistant_response": t.assistant_response,
        "user_correction": t.user_correction,
        "failure_recovery": t.failure_recovery,
        "thinking_level": t.thinking_level,
        "profile_signals": t.profile_signals,
        "error_occurred": t.error_occurred,
        "duration_ms": t.duration_ms,
        "token_count": t.token_count,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


async def get_session_summary(
    db: AsyncSession,
    session_id: str,
) -> dict:
    """Get summary stats for a trajectory session."""
    r = await db.execute(
        select(AgentTrajectoryRecord).where(
            AgentTrajectoryRecord.session_id == session_id
        ).order_by(AgentTrajectoryRecord.turn_index)
    )
    records = r.scalars().all()
    if not records:
        return {"session_id": session_id, "total_turns": 0}

    error_count = sum(1 for t in records if t.error_occurred)
    total_duration = sum(t.duration_ms or 0 for t in records)
    total_tokens = sum(t.token_count or 0 for t in records)
    tool_types = set()
    for t in records:
        for tc in (t.tool_calls or []):
            if isinstance(tc, dict):
                tool_types.add(tc.get("name", ""))
    return {
        "session_id": session_id,
        "total_turns": len(records),
        "first_turn_at": records[0].created_at.isoformat() if records[0].created_at else None,
        "last_turn_at": records[-1].created_at.isoformat() if records[-1].created_at else None,
        "error_count": error_count,
        "total_duration_ms": total_duration,
        "total_tokens": total_tokens,
        "unique_tools": sorted(tool_types),
    }
