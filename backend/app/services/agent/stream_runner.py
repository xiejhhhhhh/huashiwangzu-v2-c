import asyncio
import json
from typing import AsyncGenerator

from app.services.agent.gateway.router import gateway_router
from app.services.agent.tool_audit import (
    MAX_TOOL_ROUNDS,
    build_assistant_tool_calls,
    build_tool_specs,
    execute_tool_calls,
    parse_text_tool_calls,
    strip_text_tool_calls,
)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def stream_tool_loop(
    ctx: list[dict],
    user_id: int,
    profile_key: str,
    cancel_event: asyncio.Event,
    state: dict,
) -> AsyncGenerator[str, None]:
    tools_called: list[dict] = []
    full_thinking = ""
    for _ in range(MAX_TOOL_ROUNDS):
        stream_buffer = ""
        tool_calls: list[dict] = []
        async for event in gateway_router.chat_stream(ctx, profile_key, tools=build_tool_specs()):
            if cancel_event.is_set():
                yield _sse({"type": "cancelled"})
                return
            if event["type"] == "token":
                if event.get("tool_calls"):
                    tool_calls = event["tool_calls"]
                else:
                    stream_buffer += event["content"]
                    yield _sse(event)
            elif event["type"] == "thinking":
                full_thinking += event["content"]
                yield _sse(event)
            elif event["type"] == "error":
                yield _sse(event)
                return
            elif event["type"] == "done":
                break
        tool_calls = tool_calls or parse_text_tool_calls(stream_buffer)
        if not tool_calls:
            state.update({"reply": stream_buffer, "thinking": full_thinking, "tools_called": tools_called})
            yield _sse({
                "type": "done",
                "content": stream_buffer,
                "thinking": full_thinking,
                "tools_called": tools_called or None,
            })
            return
        ctx.append({
            "role": "assistant",
            "content": strip_text_tool_calls(stream_buffer),
            "tool_calls": build_assistant_tool_calls(tool_calls),
        })
        tools_called.extend(await execute_tool_calls(user_id, tool_calls, ctx))
        for item in tools_called:
            yield _sse({"type": "tool_call", "name": item["name"], "summary": item["result_summary"]})
    reply = "(Agent reached max tool call rounds)"
    state.update({"reply": reply, "thinking": full_thinking, "tools_called": tools_called})
    yield _sse({"type": "done", "content": reply, "thinking": full_thinking, "tools_called": tools_called or None})
