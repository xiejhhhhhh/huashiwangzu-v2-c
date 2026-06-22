"""粘滞检测：检测重复工具调用、重复报错、空响应，打断循环。

抄 OpenHands stuck detector。维护最近若干轮的
(工具名+规范化参数指纹)和(报错指纹)。"""
import hashlib
import json
import logging

logger = logging.getLogger("v2.agent.engine.粘滞检测")

STUCK_WINDOW_SIZE = 5
STUCK_THRESHOLD = 3

_round_history: dict[str, list[dict]] = {}


def _参数字典指纹(args: dict) -> str:
    normalized = json.dumps(args, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(normalized.encode()).hexdigest()


def 检测粘滞(
    tool_name: str | None,
    tool_args: dict | None,
    error_text: str | None,
    is_empty_response: bool,
    session_key: str = "default",
) -> dict:
    if session_key not in _round_history:
        _round_history[session_key] = []

    history = _round_history[session_key]
    entry = {
        "tool_name": tool_name,
        "arg_fingerprint": _参数字典指纹(tool_args) if tool_args else None,
        "error_text": error_text[:100] if error_text else None,
        "is_empty": is_empty_response,
    }
    history.append(entry)

    if len(history) > STUCK_WINDOW_SIZE:
        history.pop(0)

    if len(history) < STUCK_THRESHOLD:
        return {"stuck": False, "reason": ""}

    recent = history[-STUCK_THRESHOLD:]

    all_same_tool = all(
        e["tool_name"] is not None and e["tool_name"] == recent[0]["tool_name"]
        and e["arg_fingerprint"] is not None and e["arg_fingerprint"] == recent[0]["arg_fingerprint"]
        for e in recent
    )
    if all_same_tool:
        logger.warning("粘滞检测命中: 连续 %d 次相同工具调用 %s", STUCK_THRESHOLD, recent[0]["tool_name"])
        _round_history[session_key] = []
        return {
            "stuck": True,
            "reason": f"检测到重复操作（连续{STUCK_THRESHOLD}次相同工具: {recent[0]['tool_name']}），已停止。请换个说法或拆小任务。",
        }

    all_same_error = all(
        e["error_text"] is not None and e["error_text"] == recent[0]["error_text"]
        for e in recent
    )
    if all_same_error:
        logger.warning("粘滞检测命中: 连续 %d 次相同错误 %s", STUCK_THRESHOLD, recent[0]["error_text"])
        _round_history[session_key] = []
        return {
            "stuck": True,
            "reason": f"检测到重复错误（连续{STUCK_THRESHOLD}次: {recent[0]['error_text']}），已停止。请换个说法或拆小任务。",
        }

    all_empty = all(e["is_empty"] for e in recent)
    if all_empty:
        logger.warning("粘滞检测命中: 连续 %d 次空响应", STUCK_THRESHOLD)
        _round_history[session_key] = []
        return {
            "stuck": True,
            "reason": f"检测到连续{STUCK_THRESHOLD}次空响应，已停止。请换个说法或拆小任务。",
        }

    return {"stuck": False, "reason": ""}


def 重置(session_key: str = "default") -> None:
    _round_history.pop(session_key, None)
