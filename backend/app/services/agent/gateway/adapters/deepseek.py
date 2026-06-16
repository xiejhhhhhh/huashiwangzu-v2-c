from .base import (
    ModelAdapter,
    _extract_openai_choice,
    _build_unified,
    _build_stream_event,
)


class DeepSeekAdapter(ModelAdapter):
    def adapt_response(self, raw: dict, provider: str = "") -> dict:
        if provider == "ollama":
            msg = raw.get("message") or {}
            return _build_unified(
                content=msg.get("content", ""),
                thinking=msg.get("reasoning_content", ""),
                finish_reason=raw.get("done_reason", "stop"),
            )
        choice = _extract_openai_choice(raw)
        msg = choice.get("message") or {}
        return _build_unified(
            content=msg.get("content", ""),
            thinking=msg.get("reasoning_content", ""),
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
        if choice.get("finish_reason"):
            return _build_stream_event("done")
        if thinking:
            return _build_stream_event("thinking", thinking)
        if content:
            return _build_stream_event("token", content)
        return None
