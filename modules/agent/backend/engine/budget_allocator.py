"""动态 Token 预算装配器：估算、优先级装配、兜底、收益递减检测。"""
import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from app.gateway.config import MODEL_PROFILES
logger = logging.getLogger("v2.agent").getChild("engine.budget_allocator")
SAFETY_MAX_TOKENS = 120000
RESERVED_OUTPUT_TOKENS = 4096

# ── File-backed persistence for cross-worker consistency ──────────────
_BUDGET_DATA_DIR = Path(__file__).resolve().parents[4] / "backend" / "data" / "agent"
_BUDGET_DATA_FILE = _BUDGET_DATA_DIR / "budget_tracker.json"


def _load_budget_state() -> dict:
    if _BUDGET_DATA_FILE.exists():
        try:
            with open(_BUDGET_DATA_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("budget_tracker: failed to load state: %s", e)
    return {}


def _save_budget_state(state: dict) -> None:
    try:
        _BUDGET_DATA_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(_BUDGET_DATA_DIR), prefix=".budget_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, ensure_ascii=False)
            os.replace(tmp_path, str(_BUDGET_DATA_FILE))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as e:
        logger.warning("budget_tracker: failed to save state: %s", e)


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

    State is persisted to a file for cross-worker consistency.  Each worker
    loads the latest state before mutation and saves after each update.
    """

    def __init__(self) -> None:
        self._rounds: dict[str, list[dict]] = {}
        self._load()

    def _load(self) -> None:
        raw = _load_budget_state()
        self._rounds = raw.get("rounds", {})

    def _save(self) -> None:
        _save_budget_state({"rounds": self._rounds})

    def record_round(
        self,
        session_key: str,
        tokens_before: int,
        tokens_after: int,
    ) -> DiminishingReturnRecord:
        """Record a tool round's token counts and compute net gain."""
        self._load()
        records = self._rounds.setdefault(session_key, [])
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
        self._save()
        return rec

    def should_stop(self, session_key: str) -> tuple[bool, str]:
        """Check if recent rounds show diminishing returns.

        Returns ``(should_stop, reason)``.  Checks only the last
        ``_DIMINISHING_WINDOW`` rounds and requires at least
        ``_DIMINISHING_MIN_ROUNDS`` to have elapsed before stopping.
        """
        self._load()
        records = self._rounds.get(session_key, [])
        if len(records) < _DIMINISHING_MIN_ROUNDS:
            return False, ""

        window = records[-_DIMINISHING_WINDOW:]
        recent_gains = [r["net_gain_tokens"] for r in window]

        # All gains below threshold within the window?
        if all(g < _DIMINISHING_THRESHOLD for g in recent_gains):
            avg_gain = sum(recent_gains) // len(recent_gains)
            reason = (
                f"收益递减停止：最近{len(window)}轮平均净增{avg_gain}token"
                f"（阈值{_DIMINISHING_THRESHOLD}），"
                f"已执行{len(records)}轮"
            )
            return True, reason

        # Are gains monotonically decreasing over the window?
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

    def get_diagnosis(self, session_key: str) -> dict:
        """Return diagnostic info for the engine diagnosis output."""
        self._load()
        records = self._rounds.get(session_key, [])
        return {
            "total_rounds": len(records),
            "recent_gains": [r["net_gain_tokens"] for r in records[-_DIMINISHING_WINDOW:]],
            "window_size": _DIMINISHING_WINDOW,
            "threshold": _DIMINISHING_THRESHOLD,
        }

    def reset(self, session_key: str) -> None:
        """Clear tracking for a given session."""
        self._load()
        self._rounds.pop(session_key, None)
        self._save()


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


def _group_projected_messages(projected_messages: list[dict]) -> list[list[dict]]:
    """Group projected messages into atomic units.

    A tool round must stay intact:
    assistant message with tool_calls + following tool messages that share
    the same llm_response_id should be treated as one unit, so budget
    trimming never leaves the model with an orphan assistant/tool pair.
    """
    grouped: list[list[dict]] = []
    i = 0
    while i < len(projected_messages):
        msg = projected_messages[i]
        unit = [msg]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_call_count = len(msg.get("tool_calls") or [])
            j = i + 1
            seen_tool_msgs = 0
            while j < len(projected_messages) and seen_tool_msgs < tool_call_count:
                next_msg = projected_messages[j]
                if next_msg.get("role") != "tool":
                    break
                unit.append(next_msg)
                seen_tool_msgs += 1
                j += 1
            grouped.append(unit)
            i = j
            continue
        grouped.append(unit)
        i += 1
    return grouped


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
    for group in _group_projected_messages(projected_messages):
        group_tokens = sum(estimate_one_message(msg) for msg in group)
        if not group:
            continue
        if group[0]["role"] not in ("user", "assistant", "tool"):
            continue
        if recent_tokens + group_tokens <= remaining:
            recent.extend(group)
            recent_tokens += group_tokens
        else:
            dropped += len(group)
    diagnosis["recent_tokens"] = recent_tokens
    diagnosis["dropped_recent_count"] = dropped
    messages.extend(recent)
    messages.append(input_msg)
    total_est = system_tokens + input_tokens + recent_tokens
    diagnosis["total_estimated"] = total_est
    diagnosis["budget_exceeded"] = total_est > budget
    return messages, diagnosis
