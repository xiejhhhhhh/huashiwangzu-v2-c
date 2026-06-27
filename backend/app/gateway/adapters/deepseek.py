from app.gateway.contract import ModelResponse, StreamEvent, StreamEventType, ToolCall

from .base import (
    ModelAdapter,
    _build_stream_event,
    _build_unified,
    _extract_ollama_tool_calls,
    _extract_openai_choice,
    _extract_openai_tool_calls,
    _extract_usage,
)


class DeepSeekAdapter(ModelAdapter):
    def adapt_response(self, raw: dict, provider: str = "") -> ModelResponse:
        usage = _extract_usage(raw)
        if provider == "ollama":
            msg = raw.get("message") or {}
            return _build_unified(
                content=msg.get("content", ""),
                thinking=msg.get("reasoning_content", ""),
                tool_calls=_extract_ollama_tool_calls(raw),
                finish_reason=raw.get("done_reason", "stop"),
                usage=usage,
            )
        choice = _extract_openai_choice(raw)
        msg = choice.get("message") or {}
        tool_calls = _extract_openai_tool_calls(choice)
        return _build_unified(
            content=msg.get("content", ""),
            thinking=msg.get("reasoning_content", ""),
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
            thinking = msg.get("reasoning_content", "")
            if thinking:
                return _build_stream_event(StreamEventType.THINKING, thinking)
            if content:
                return _build_stream_event(StreamEventType.TOKEN, content)
            return None
        choice = _extract_openai_choice(chunk)
        delta = choice.get("delta") or {}
        content = delta.get("content", "")
        thinking = delta.get("reasoning_content", "")
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            tool_calls_list = _extract_openai_tool_calls(choice)
            if not tool_calls_list:
                tool_calls_list = _extract_delta_tool_calls(delta)
            return StreamEvent(
                type=StreamEventType.TOKEN,
                content=content or "",
                tool_calls=tool_calls_list,
            )
        if choice.get("finish_reason"):
            usage = _extract_usage(chunk)
            return _build_stream_event(StreamEventType.DONE, usage=usage)
        if thinking:
            return _build_stream_event(StreamEventType.THINKING, thinking)
        if content:
            return _build_stream_event(StreamEventType.TOKEN, content)
        return None


def _extract_delta_tool_calls(delta: dict) -> list[ToolCall]:
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
        result.append(ToolCall(
            id=tc.get("id", ""),
            type="function",
            function={"name": fn.get("name", ""), "arguments": args},
        ))
    return result
