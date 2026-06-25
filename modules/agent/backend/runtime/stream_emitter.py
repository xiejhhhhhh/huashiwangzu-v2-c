"""StreamEmitter — reusable SSE content streamer with inline-tool recovery.

Extracted from the old ``_yield_final_stream()`` in ``chat.py``.
Wraps the streaming model call, buffers token events, checks for
inline XML tool calls, and yields properly formatted SSE events.
"""

from __future__ import annotations

import json
import logging

from ..engine.engine import chat_stream_with_degradation_chain
from ..engine.failure_diagnostics import record_failure
from ..services.model_client import parse_inline_tool_calls

logger = logging.getLogger("v2.agent").getChild("runtime.stream_emitter")


class StreamEmitter:
    """Emit final-content SSE events, with inline tool-call recovery.

    Usage::

        emitter = StreamEmitter()
        async for event in emitter.yield_final_stream(messages, profile_key, ...):
            if isinstance(event, dict) and event.get("type") == "_inline_tool_calls":
                # caller should re-enter tool loop
                ...
            else:
                yield event   # raw bytes for StreamingResponse
    """

    async def yield_final_stream(
        self,
        messages: list[dict],
        profile_key: str = "deepseek-v4-flash",
        tools: list[dict] | None = None,
        conversation_id: int | None = None,
        owner_id: int | None = None,
        *,
        full_buffer: list[str] | None = None,
        thinking_buffer: list[str] | None = None,
        timeline: list[dict] | None = None,
    ):
        """Stream final content, buffering events for post-processing.

        Yields ``bytes`` (SSE ``data: ...`` frames).  If inline XML tool
        calls are found *after* streaming completes, yields a single
        ``{"type": "_inline_tool_calls", "tool_calls": [...]}`` dict
        instead of flushing buffered token events — the caller should
        re-enter its tool loop when it sees this dict.

        Parameters mirror those of the old ``_yield_final_stream``.
        """
        logger.info("[DIAG] StreamEmitter.yield_final_stream ENTER")
        event_count = 0
        token_buffer: list[tuple[str, str]] = []
        full = full_buffer if full_buffer is not None else []
        thinking_parts = thinking_buffer if thinking_buffer is not None else []
        tl = timeline if timeline is not None else []

        try:
            async for event in chat_stream_with_degradation_chain(
                messages, profile_key, tools,
                conversation_id=conversation_id,
            ):
                event_count += 1
                event_type = event.get("type")
                content = str(event.get("content") or "")
                logger.info(
                    "[DIAG] StreamEmitter event #%d type=%s content_len=%d",
                    event_count, event_type, len(content),
                )
                if event_type == "thinking" and content:
                    thinking_parts.append(content)
                    tl.append({"type": "thinking", "content": content})
                    yield self._sse("thinking", content)
                elif event_type in ("token", "content") and content:
                    full.append(content)
                    tl.append({"type": "text", "content": content})
                    token_buffer.append((event_type, content))
                elif event_type == "error" and content:
                    yield self._sse("error", content)
                elif event_type == "done":
                    logger.info(
                        "[DIAG] StreamEmitter got done event — stream ending",
                    )

            full_content = "".join(full)
            try:
                clean_content, inline_calls = parse_inline_tool_calls(full_content)
            except Exception as exc:
                logger.warning(
                    "StreamEmitter parse_inline_tool_calls failed: %s", exc,
                )
                clean_content, inline_calls = full_content, []

            if inline_calls:
                full.clear()
                full.append(clean_content)
                logger.info(
                    "[DIAG] StreamEmitter found %d inline tool calls, "
                    "re-entering tool loop", len(inline_calls),
                )
                yield {"type": "_inline_tool_calls", "tool_calls": inline_calls}
                return

            for etype, econtent in token_buffer:
                yield self._sse("token", econtent)

            logger.info(
                "[DIAG] StreamEmitter EXIT after %d events — no inline calls",
                event_count,
            )
        except Exception as exc:
            logger.exception("StreamEmitter unexpected error: %s", exc)
            await record_failure(
                "chat", "yield_final_stream",
                type(exc).__name__, str(exc),
                conversation_id, owner_id,
            )
            yield self._sse(
                "error", f"(stream error: {exc})",
            )

    @staticmethod
    def _sse(event_type: str, content: str) -> bytes:
        """Format a single SSE ``data:`` frame."""
        return (
            f"data: {json.dumps({'type': event_type, 'content': content}, ensure_ascii=False)}\n\n"
        ).encode("utf-8")
