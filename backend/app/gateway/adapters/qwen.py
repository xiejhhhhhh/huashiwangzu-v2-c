from app.gateway.contract import ModelResponse, StreamEvent, StreamEventType

from .base import (
    ModelAdapter,
    _build_stream_event,
    _build_unified,
    _extract_ollama_content,
    _extract_ollama_tool_calls,
    _extract_openai_choice,
    _extract_openai_tool_calls,
    _extract_usage,
)


class QwenAdapter(ModelAdapter):
    def adapt_response(self, raw: dict, provider: str = "") -> ModelResponse:
        usage = _extract_usage(raw)
        if provider == "ollama":
            content = _extract_ollama_content(raw)
            tool_calls = _extract_ollama_tool_calls(raw)
            return _build_unified(content=content, tool_calls=tool_calls, usage=usage)
        choice = _extract_openai_choice(raw)
        msg = choice.get("message") or {}
        tool_calls = _extract_openai_tool_calls(choice)
        return _build_unified(
            content=msg.get("content", ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=usage,
        )

    def adapt_stream_chunk(self, chunk: dict, provider: str = "") -> StreamEvent | None:
        if provider == "ollama":
            if chunk.get("done"):
                return _build_stream_event(StreamEventType.DONE)
            msg = chunk.get("message") or {}
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                return StreamEvent(
                    type=StreamEventType.TOKEN,
                    content=content or "",
                    tool_calls=_extract_ollama_tool_calls(chunk),
                )
            if content:
                return _build_stream_event(StreamEventType.TOKEN, content)
            return None
        choice = _extract_openai_choice(chunk)
        delta = choice.get("delta") or {}
        content = delta.get("content", "")
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            return StreamEvent(
                type=StreamEventType.TOKEN,
                content=content or "",
                tool_calls=_extract_openai_tool_calls(choice),
            )
        if choice.get("finish_reason"):
            usage = _extract_usage(chunk)
            return _build_stream_event(StreamEventType.DONE, usage=usage)
        if content:
            return _build_stream_event(StreamEventType.TOKEN, content)
        return None
