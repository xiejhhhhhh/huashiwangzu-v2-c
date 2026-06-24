"""动态 Token 预算装配器：估算、优先级装配、兜底、收益递减检测。"""
import json
import logging
import math
from dataclasses import dataclass, field

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.router import MODEL_PROFILES
from ..models import AgentBudgetState

logger = logging.getLogger("v2.agent").getChild("engine.budget_allocator")
SAFETY_MAX_TOKENS = 120000
RESERVED_OUTPUT_TOKENS = 4096

# ── DB-backed persistence for cross-worker consistency ────────────────


# ── Diminishing returns tracker ────────────────────────────────────────────
#
# Detects when repeated tool rounds produce negligible incremental information,
# so the engine can stop early instead of burning tokens on near-zero-gain turns.


@dataclass
class DiminishingReturnRecord:
    """One round's measured information gain."""
    turn_index: int
    token_count_before: int
    token_count_after: int
    net_gain_tokens: int
    stopped_reason: str = ""


_DIMINISHING_WINDOW = 3       # how many recent rounds to evaluate
_DIMINISHING_THRESHOLD = 500   # minimum net token gain to consider "valuable"
_DIMINISHING_MIN_ROUNDS = 3    # don't stop before this many rounds


class DiminishingBudgetTracker:
    """Tracks multi-turn tool round information gain and decides when to stop.

    State is persisted to DB for cross-worker consistency.
    Each conversation has one row identified by conversation_id (derived from session_key).
    """

    def __init__(self) -> None:
        self._rounds: dict[str, list[dict]] = {}

    async def _load_from_db(self, db: AsyncSession, session_key: str) -> list[dict]:
        conv_id = self._conv_id(session_key)
        r = await db.execute(
            select(AgentBudgetState).where(AgentBudgetState.conversation_id == conv_id)
        )
        row = r.scalar_one_or_none()
        return (row.rounds_data or {}).get("rounds", []) if row else []

    async def _save_to_db(self, db: AsyncSession, session_key: str, records: list[dict]) -> None:
        conv_id = self._conv_id(session_key)
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(AgentBudgetState).values(
            conversation_id=conv_id, rounds_data={"rounds": records},
        )
        stmt = stmt.on_conflict_do_update(
            constraint="agent_budget_states_conversation_id_key",
            set_={"rounds_data": {"rounds": records}},
        )
        await db.execute(stmt)
        await db.commit()

    @staticmethod
    def _conv_id(session_key: str) -> int:
        conv_part = session_key.replace("budget_conv_", "").replace("conv_", "")
        try:
            return int(conv_part)
        except (ValueError, TypeError):
            return hash(session_key) % (10 ** 9)

    async def record_round(
        self,
        db: AsyncSession,
        session_key: str,
        tokens_before: int,
        tokens_after: int,
    ) -> DiminishingReturnRecord:
        """Record a tool round's token counts and compute net gain."""
        records = await self._load_from_db(db, session_key)
        net_gain = max(tokens_after - tokens_before, 0)
        turn_index = len(records)
        rec = DiminishingReturnRecord(
            turn_index=turn_index,
            token_count_before=tokens_before,
            token_count_after=tokens_after,
            net_gain_tokens=net_gain,
        )
        records.append({
            "turn_index": turn_index,
            "token_count_before": tokens_before,
            "token_count_after": tokens_after,
            "net_gain_tokens": net_gain,
        })
        await self._save_to_db(db, session_key, records)
        return rec

    async def should_stop(self, db: AsyncSession, session_key: str) -> tuple[bool, str]:
        """Check if recent rounds show diminishing returns.

        Returns ``(should_stop, reason)``.  Checks only the last
        ``_DIMINISHING_WINDOW`` rounds and requires at least
        ``_DIMINISHING_MIN_ROUNDS`` to have elapsed before stopping.
        """
        records = await self._load_from_db(db, session_key)
        if len(records) < _DIMINISHING_MIN_ROUNDS:
            return False, ""

        window = records[-_DIMINISHING_WINDOW:]
        recent_gains = [r["net_gain_tokens"] for r in window]

        if all(g < _DIMINISHING_THRESHOLD for g in recent_gains):
            avg_gain = sum(recent_gains) // len(recent_gains)
            reason = (
                f"收益递减停止：最近{len(window)}轮平均净增{avg_gain}token"
                f"（阈值{_DIMINISHING_THRESHOLD}），"
                f"已执行{len(records)}轮"
            )
            return True, reason

        if len(window) >= 3 and all(
            window[i]["net_gain_tokens"] > window[i + 1]["net_gain_tokens"]
            for i in range(len(window) - 1)
        ):
            last_gain = window[-1]["net_gain_tokens"]
            reason = (
                f"收益递减停止：连续{len(window)}轮净增益单调下降，"
                f"末轮仅{last_gain}token（阈值{_DIMINISHING_THRESHOLD}），"
                f"已执行{len(records)}轮"
            )
            return True, reason

        return False, ""

    async def get_diagnosis(self, db: AsyncSession, session_key: str) -> dict:
        """Return diagnostic info for the engine diagnosis output."""
        records = await self._load_from_db(db, session_key)
        return {
            "total_rounds": len(records),
            "recent_gains": [r["net_gain_tokens"] for r in records[-_DIMINISHING_WINDOW:]],
            "window_size": _DIMINISHING_WINDOW,
            "threshold": _DIMINISHING_THRESHOLD,
        }

    async def reset(self, db: AsyncSession, session_key: str) -> None:
        """Clear tracking for a given session."""
        conv_id = self._conv_id(session_key)
        await db.execute(
            sa_delete(AgentBudgetState).where(AgentBudgetState.conversation_id == conv_id)
        )
        await db.commit()


def get_context_budget(profile_key: str) -> int | None:
    profile = MODEL_PROFILES.get(profile_key, {})
    budget = profile.get("context_budget")
    if budget is not None:
        try:
            return int(budget)
        except (TypeError, ValueError):
            return None
    return None


def estimate_tokens(messages: list[dict]) -> int:
    text = ""
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text += part.get("text", "")
                elif isinstance(part, str):
                    text += part
        elif isinstance(content, str):
            text += content
        # tool_calls
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            text += fn.get("name", "") + json.dumps(fn.get("arguments", {}), ensure_ascii=False)
        text += m.get("role", "") + m.get("name", "")
    token_estimate = math.ceil(len(text) / 1.5)
    return max(token_estimate, 0)


def estimate_one_message(msg: dict) -> int:
    text = msg.get("content", "")
    if isinstance(text, str):
        return max(math.ceil(len(text) / 1.5), 0)
    return 0


def assemble_context(
    projected_messages: list[dict],
    system_content: str,
    current_input: str,
    profile_key: str,
) -> tuple[list[dict], dict]:
    budget = get_context_budget(profile_key)
    diagnosis = {
        "budget": budget,
        "total_estimated": 0,
        "system_tokens": 0,
        "input_tokens": 0,
        "recent_tokens": 0,
        "dropped_recent_count": 0,
        "is_unlimited": budget is None,
        "budget_exceeded": False,
    }
    system_msg = {"role": "system", "content": system_content}
    system_tokens = estimate_one_message(system_msg)
    diagnosis["system_tokens"] = system_tokens
    input_msg = {"role": "user", "content": current_input}
    input_tokens = estimate_one_message(input_msg)
    diagnosis["input_tokens"] = input_tokens
    required_tokens = system_tokens + input_tokens + RESERVED_OUTPUT_TOKENS
    messages: list[dict] = [system_msg]
    if budget is None:
        budget = SAFETY_MAX_TOKENS
        diagnosis["is_unlimited"] = True
        diagnosis["budget"] = budget
    remaining = budget - required_tokens
    if remaining <= 0:
        messages.append(input_msg)
        total_recent = sum(estimate_one_message(m) for m in projected_messages)
        diagnosis["total_estimated"] = system_tokens + input_tokens + total_recent
        diagnosis["recent_tokens"] = total_recent
        diagnosis["budget_exceeded"] = True
        return messages, diagnosis
    # Fill with recent dialog messages from the projected events
    recent: list[dict] = []
    recent_tokens = 0
    dropped = 0
    for msg in projected_messages:
        if msg["role"] not in ("user", "assistant", "tool"):
            continue
        mt = estimate_one_message(msg)
        if recent_tokens + mt <= remaining:
            recent.append(msg)
            recent_tokens += mt
        else:
            dropped += 1
    diagnosis["recent_tokens"] = recent_tokens
    diagnosis["dropped_recent_count"] = dropped
    messages.extend(recent)
    messages.append(input_msg)
    total_est = system_tokens + input_tokens + recent_tokens
    diagnosis["total_estimated"] = total_est
    diagnosis["budget_exceeded"] = total_est > budget
    return messages, diagnosis
