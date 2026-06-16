from .base import (
    ModelAdapter,
    _extract_ollama_content,
    _extract_ollama_tool_calls,
    _extract_openai_choice,
    _extract_openai_tool_calls,
    _build_unified,
    _build_stream_event,
)


class GemmaAdapter(ModelAdapter):
    def adapt_response(self, raw: dict, provider: str = "") -> dict:
        if provider == "ollama":
            content = _extract_ollama_content(raw)
            tool_calls = _extract_ollama_tool_calls(raw)
            return _build_unified(content=content, tool_calls=tool_calls)
        choice = _extract_openai_choice(raw)
        msg = choice.get("message") or {}
        tool_calls = _extract_openai_tool_calls(choice)
        return _build_unified(
            content=msg.get("content", ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    def adapt_stream_chunk(self, chunk: dict, provider: str = "") -> dict | None:
        if provider == "ollama":
            if chunk.get("done"):
                return _build_stream_event("done")
            msg = chunk.get("message") or {}
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                return {
                    "type": "token",
                    "content": content or "",
                    "tool_calls": _extract_ollama_tool_calls(chunk),
                }
            if content:
                return _build_stream_event("token", content)
            return None
        choice = _extract_openai_choice(chunk)
        delta = choice.get("delta") or {}
        content = delta.get("content", "")
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            return {
                "type": "token",
                "content": content or "",
                "tool_calls": _extract_openai_tool_calls(choice),
            }
        if choice.get("finish_reason"):
            return _build_stream_event("done")
        if content:
            return _build_stream_event("token", content)
        return None
