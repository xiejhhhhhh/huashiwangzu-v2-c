from .base import (
    ModelAdapter,
    _build_stream_event,
    _build_unified,
    _extract_ollama_tool_calls,
    _extract_openai_choice,
    _extract_openai_tool_calls,
)


class DeepSeekAdapter(ModelAdapter):
    def adapt_response(self, raw: dict, provider: str = "") -> dict:
        if provider == "ollama":
            msg = raw.get("message") or {}
            return _build_unified(
                content=msg.get("content", ""),
                thinking=msg.get("reasoning_content", ""),
                tool_calls=_extract_ollama_tool_calls(raw),
                finish_reason=raw.get("done_reason", "stop"),
            )
        choice = _extract_openai_choice(raw)
        msg = choice.get("message") or {}
        tool_calls = _extract_openai_tool_calls(choice)
        return _build_unified(
            content=msg.get("content", ""),
            thinking=msg.get("reasoning_content", ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    def adapt_stream_chunk(self, chunk: dict, provider: str = "") -> dict | None:
        if provider == "ollama":
            if chunk.get("done"):
                return _build_stream_event("done")
            msg = chunk.get("message") or {}
            content = msg.get("content", "")
            thinking = msg.get("reasoning_content", "")
            if thinking:
                return _build_stream_event("thinking", thinking)
            if content:
                return _build_stream_event("token", content)
            return None
        choice = _extract_openai_choice(chunk)
        delta = choice.get("delta") or {}
        content = delta.get("content", "")
        thinking = delta.get("reasoning_content", "")
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            tool_calls_list = _extract_openai_tool_calls(choice)
            # If _extract_openai_tool_calls returned empty (delta path),
            # read directly from delta.tool_calls
            if not tool_calls_list:
                tool_calls_list = _extract_delta_tool_calls(delta)
            return {
                "type": "token",
                "content": content or "",
                "tool_calls": tool_calls_list,
            }
        if choice.get("finish_reason"):
            return _build_stream_event("done")
        if thinking:
            return _build_stream_event("thinking", thinking)
        if content:
            return _build_stream_event("token", content)
        return None


def _extract_delta_tool_calls(delta: dict) -> list[dict]:
    """Extract tool_calls from streaming delta (one chunk at a time)."""
    raw_calls = delta.get("tool_calls") or []
    result = []
    for tc in raw_calls:
        fn = tc.get("function", {})
        args = fn.get("arguments", "")
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        result.append({
            "id": tc.get("id", ""),
            "index": tc.get("index", 0),
            "type": "function",
            "function": {
                "name": fn.get("name", ""),
                "arguments": args,
            },
        })
    return result
