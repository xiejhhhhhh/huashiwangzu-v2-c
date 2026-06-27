"""Streaming LLM diagnostics with TTFT measurement for knowledge module.

Adds first-token timing alongside existing non-streaming path.
"""
from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from typing import Any

from .llm_diagnostics import _RETRY_COUNT_NOTE, _extra_text, _message_chars, _user_chars

ChatMessage = Mapping[str, str]


async def timed_llm_chat_stream(
    *,
    logger: logging.Logger,
    stage: str,
    profile_key: str,
    messages: Sequence[ChatMessage],
    chat_stream_func: Callable[..., AsyncGenerator[dict, None]],
    document_id: int | None = None,
    page: int | None = None,
    extra: Mapping[str, object] | None = None,
    fallback_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Streaming LLM call recording TTFT + total stream time.

    Yields the same ``{"content": ..., "tokens": ...}`` dict shape as the
    non-streaming ``gateway_router.chat()`` so callers are interchangeable.

    When streaming fails (error event / exception) and *fallback_func* is
    provided, the call degrades gracefully to the non-streaming path.
    """
    input_chars = _message_chars(messages)
    user_chars = _user_chars(messages)
    extra_fields = _extra_text(extra)
    started = time.perf_counter()

    logger.info(
        "LLM_STREAM_START stage=%s profile_key=%s document_id=%s page=%s "
        "input_chars=%d user_chars=%d retry_count=%s%s",
        stage,
        profile_key,
        document_id,
        page,
        input_chars,
        user_chars,
        _RETRY_COUNT_NOTE,
        extra_fields,
    )

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    first_chunk_ms: float | None = None
    first_token_ms: float | None = None
    first_token_chars: int = 0
    saw_token = False
    stream_failed = False
    fail_reason = ""

    try:
        async for event in chat_stream_func(messages=list(messages), profile_key=profile_key):
            if first_chunk_ms is None:
                first_chunk_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "LLM_STREAM_FIRST_CHUNK stage=%s profile_key=%s document_id=%s page=%s "
                    "first_chunk_ms=%.1f retry_count=%s%s",
                    stage,
                    profile_key,
                    document_id,
                    page,
                    first_chunk_ms,
                    _RETRY_COUNT_NOTE,
                    extra_fields,
                )

            event_type = event.get("type", "")
            event_content = event.get("content", "")

            if event_type == "token":
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - started) * 1000
                    logger.info(
                        "LLM_STREAM_TTFT stage=%s profile_key=%s document_id=%s page=%s "
                        "ttft_ms=%.1f retry_count=%s%s",
                        stage,
                        profile_key,
                        document_id,
                        page,
                        first_token_ms,
                        _RETRY_COUNT_NOTE,
                        extra_fields,
                    )
                if not saw_token:
                    first_token_chars = len(event_content)
                    saw_token = True
                content_parts.append(event_content)
            elif event_type == "thinking":
                reasoning_parts.append(event_content)
            elif event_type == "done":
                break
            elif event_type == "error":
                stream_failed = True
                fail_reason = event_content
                logger.warning(
                    "LLM_STREAM_EVENT_ERROR stage=%s profile_key=%s document_id=%s page=%s "
                    "error=%s retry_count=%s%s",
                    stage,
                    profile_key,
                    document_id,
                    page,
                    fail_reason,
                    _RETRY_COUNT_NOTE,
                    extra_fields,
                )
                break
    except Exception as exc:
        stream_failed = True
        fail_reason = f"{type(exc).__name__}: {exc}"
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.warning(
            "LLM_STREAM_EXCEPTION stage=%s profile_key=%s document_id=%s page=%s "
            "elapsed_ms=%.1f error_type=%s error=%s retry_count=%s%s",
            stage,
            profile_key,
            document_id,
            page,
            elapsed_ms,
            type(exc).__name__,
            exc,
            _RETRY_COUNT_NOTE,
            extra_fields,
        )

    if stream_failed:
        if fallback_func is not None:
            logger.info(
                "LLM_STREAM_FALLBACK stage=%s profile_key=%s document_id=%s page=%s "
                "reason=%s retry_count=%s%s",
                stage,
                profile_key,
                document_id,
                page,
                fail_reason,
                _RETRY_COUNT_NOTE,
                extra_fields,
            )
            try:
                result = await fallback_func(messages=list(messages), profile_key=profile_key)
                diagnostics = result.get("diagnostics") or {}
                trace_id = diagnostics.get("trace_id", "N/A")
                logger.info(
                    "LLM_STREAM_FALLBACK_DONE stage=%s profile_key=%s document_id=%s page=%s "
                    "trace_id=%s retry_count=%s%s",
                    stage,
                    profile_key,
                    document_id,
                    page,
                    trace_id,
                    _RETRY_COUNT_NOTE,
                    extra_fields,
                )
                return result
            except Exception as fb_exc:
                logger.error(
                    "LLM_STREAM_FALLBACK_ERROR stage=%s profile_key=%s document_id=%s page=%s "
                    "error_type=%s error=%s retry_count=%s%s",
                    stage,
                    profile_key,
                    document_id,
                    page,
                    type(fb_exc).__name__,
                    fb_exc,
                    _RETRY_COUNT_NOTE,
                    extra_fields,
                )
                raise
        logger.warning(
            "LLM_STREAM_FAILED_NORETRY stage=%s profile_key=%s document_id=%s page=%s "
            "reason=%s (no fallback) retry_count=%s%s",
            stage,
            profile_key,
            document_id,
            page,
            fail_reason,
            _RETRY_COUNT_NOTE,
            extra_fields,
        )
        return {"content": "", "tokens": 0}

    stream_total_ms = (time.perf_counter() - started) * 1000
    full_content = "".join(content_parts)
    reasoning_content = "".join(reasoning_parts)
    output_chars = len(full_content)
    reasoning_chars_val = len(reasoning_content)
    estimated_tokens = max(output_chars // 4, 0)

    logger.info(
        "LLM_STREAM_END stage=%s profile_key=%s document_id=%s page=%s "
        "first_chunk_ms=%.1f ttft_ms=%.1f stream_total_ms=%.1f input_chars=%d output_chars=%d "
        "first_token_chars=%d reasoning_chars=%d tokens=%d ok=%d "
        "retry_count=%s%s",
        stage,
        profile_key,
        document_id,
        page,
        first_chunk_ms or 0,
        first_token_ms or 0,
        stream_total_ms,
        input_chars,
        output_chars,
        first_token_chars,
        reasoning_chars_val,
        estimated_tokens,
        1 if full_content.strip() else 0,
        _RETRY_COUNT_NOTE,
        extra_fields,
    )

    return {"content": full_content, "tokens": estimated_tokens}
