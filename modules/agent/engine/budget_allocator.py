"""动态 Token 预算装配器：估算、优先级装配、兜底。"""
import json
import logging
import math
from app.gateway.router import MODEL_PROFILES
logger = logging.getLogger("v2.agent.engine.预算分配器")
SAFETY_MAX_TOKENS = 120000
RESERVED_OUTPUT_TOKENS = 4096


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
