from __future__ import annotations

import json


class GatewayProtocolError(ValueError):
    """Raised when outbound OpenAI-compatible messages violate protocol."""


_OPENAI_ROLES = {"system", "user", "assistant", "tool"}


def normalize_openai_messages(messages: list[dict]) -> list[dict]:
    """Normalize and validate messages before sending to OpenAI-compatible APIs.

    DeepSeek/OpenAI require every assistant message with ``tool_calls`` to be
    followed immediately by one ``tool`` message for each ``tool_call_id``.
    This function enforces that contract locally so malformed internal history
    never reaches the external model provider.
    """
    normalized: list[dict] = []
    i = 0
    while i < len(messages):
        msg = _normalize_message(messages[i], i)
        normalized.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if msg.get("role") == "assistant" and tool_calls:
            expected_ids = [_tool_call_id(tc, i) for tc in tool_calls]
            seen_ids: list[str] = []
            j = i + 1
            while j < len(messages) and messages[j].get("role") == "tool":
                tool_msg = _normalize_message(messages[j], j)
                tool_call_id = str(tool_msg.get("tool_call_id") or "")
                if tool_call_id not in expected_ids:
                    raise GatewayProtocolError(
                        f"tool message at index {j} has unknown tool_call_id '{tool_call_id}'"
                    )
                if tool_call_id in seen_ids:
                    raise GatewayProtocolError(
                        f"duplicate tool result for tool_call_id '{tool_call_id}' at index {j}"
                    )
                normalized.append(tool_msg)
                seen_ids.append(tool_call_id)
                j += 1

            missing = [tool_id for tool_id in expected_ids if tool_id not in seen_ids]
            if missing:
                raise GatewayProtocolError(
                    "assistant tool_calls missing matching tool results: " + ", ".join(missing)
                )
            i = j
            continue

        if msg.get("role") == "tool":
            raise GatewayProtocolError(
                f"orphan tool message at index {i}: no preceding assistant tool_calls"
            )
        i += 1
    return normalized


def normalize_openai_tools(tools: list[dict] | None) -> list[dict] | None:
    """Normalize tool definitions to OpenAI-compatible function schema."""
    if not tools:
        return None
    normalized: list[dict] = []
    for idx, tool in enumerate(tools):
        if not isinstance(tool, dict):
            raise GatewayProtocolError(f"tool at index {idx} must be an object")
        if tool.get("type") not in (None, "function"):
            raise GatewayProtocolError(f"tool at index {idx} has unsupported type '{tool.get('type')}'")
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = str(fn.get("name") or "").strip()
        if not name:
            raise GatewayProtocolError(f"tool at index {idx} is missing function.name")
        parameters = fn.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {"type": "object", "properties": {}}
        normalized.append({
            "type": "function",
            "function": {
                "name": name,
                "description": str(fn.get("description") or ""),
                "parameters": parameters,
            },
        })
    return normalized


def normalize_openai_payload(messages: list[dict], tools: list[dict] | None) -> tuple[list[dict], list[dict] | None]:
    return normalize_openai_messages(messages), normalize_openai_tools(tools)


def is_protocol_error_text(text: str) -> bool:
    lowered = (text or "").lower()
    markers = (
        "invalid_request_error",
        "bad request",
        "tool_calls must be followed",
        "tool messages responding to each",
        "insufficient tool messages",
        "messages malformed",
        "orphan tool message",
        "missing matching tool results",
        "tool_call_id",
    )
    return any(marker in lowered for marker in markers)


def _normalize_message(msg: dict, index: int) -> dict:
    if not isinstance(msg, dict):
        raise GatewayProtocolError(f"message at index {index} must be an object")
    role = msg.get("role")
    if role not in _OPENAI_ROLES:
        raise GatewayProtocolError(f"message at index {index} has unsupported role '{role}'")

    normalized = dict(msg)
    if role == "assistant" and normalized.get("tool_calls"):
        normalized["content"] = _normalize_content(normalized.get("content"), allow_empty=True)
        normalized["tool_calls"] = [_normalize_tool_call(tc, index) for tc in normalized.get("tool_calls") or []]
    elif role == "tool":
        tool_call_id = str(normalized.get("tool_call_id") or "").strip()
        if not tool_call_id:
            raise GatewayProtocolError(f"tool message at index {index} is missing tool_call_id")
        normalized["tool_call_id"] = tool_call_id
        normalized["content"] = _normalize_content(normalized.get("content"), allow_empty=True)
    else:
        normalized["content"] = _normalize_content(normalized.get("content"), allow_empty=True)
        normalized.pop("tool_calls", None)
        normalized.pop("tool_call_id", None)
    return normalized


def _normalize_tool_call(tool_call: dict, message_index: int) -> dict:
    if not isinstance(tool_call, dict):
        raise GatewayProtocolError(f"tool_call in message {message_index} must be an object")
    fn = tool_call.get("function") or {}
    if not isinstance(fn, dict):
        raise GatewayProtocolError(f"tool_call in message {message_index} has invalid function")
    tool_id = str(tool_call.get("id") or "").strip()
    name = str(fn.get("name") or "").strip()
    if not tool_id:
        raise GatewayProtocolError(f"tool_call in message {message_index} is missing id")
    if not name:
        raise GatewayProtocolError(f"tool_call '{tool_id}' is missing function.name")
    return {
        "id": tool_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": _normalize_arguments(fn.get("arguments", "{}")),
        },
    }


def _tool_call_id(tool_call: dict, message_index: int) -> str:
    tool_id = str(tool_call.get("id") or "").strip()
    if not tool_id:
        raise GatewayProtocolError(f"tool_call in message {message_index} is missing id")
    return tool_id


def _normalize_arguments(arguments: object) -> str:
    if isinstance(arguments, str):
        return arguments
    try:
        return json.dumps(arguments if arguments is not None else {}, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"value": str(arguments)}, ensure_ascii=False)


def _normalize_content(content: object, *, allow_empty: bool = False) -> str:
    if content is None:
        return "" if allow_empty else " "
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except Exception:
        return str(content)
