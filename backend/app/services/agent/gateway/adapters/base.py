from abc import ABC, abstractmethod


class ModelAdapter(ABC):
    @abstractmethod
    def adapt_response(self, raw: dict, provider: str = "") -> dict:
        ...

    @abstractmethod
    def adapt_stream_chunk(self, chunk: dict, provider: str = "") -> dict | None:
        ...


def _extract_ollama_content(raw: dict) -> str:
    return (raw.get("message") or {}).get("content", "")


def _extract_ollama_tool_calls(raw: dict) -> list:
    msg = raw.get("message") or {}
    raw_calls = msg.get("tool_calls") or []
    result = []
    for tc in raw_calls:
        fn = tc.get("function", {})
        args_str = fn.get("arguments", {})
        if isinstance(args_str, str):
            import json
            try:
                args_str = json.loads(args_str)
            except json.JSONDecodeError:
                args_str = {}
        result.append({
            "id": tc.get("id", ""),
            "type": "function",
            "function": {
                "name": fn.get("name", ""),
                "arguments": args_str,
            },
        })
    return result


def _extract_openai_tool_calls(choice: dict) -> list:
    msg = choice.get("message") or {}
    raw_calls = msg.get("tool_calls") or []
    result = []
    for tc in raw_calls:
        fn = tc.get("function", {})
        args = fn.get("arguments", "{}")
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        result.append({
            "id": tc.get("id", ""),
            "type": "function",
            "function": {
                "name": fn.get("name", ""),
                "arguments": args,
            },
        })
    return result


def _extract_openai_choice(raw: dict, idx: int = 0) -> dict:
    choices = raw.get("choices") or []
    if idx < len(choices):
        return choices[idx]
    return {}


def _build_unified(
    content: str = "",
    thinking: str = "",
    tool_calls: list | None = None,
    finish_reason: str = "stop",
) -> dict:
    return {
        "content": content,
        "thinking": thinking,
        "tool_calls": tool_calls or [],
        "finish_reason": finish_reason,
    }


def _build_stream_event(
    event_type: str,
    content: str = "",
) -> dict:
    return {"type": event_type, "content": content}



