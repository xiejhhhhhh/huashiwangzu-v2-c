import asyncio
import json
import logging
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import ChatMessage, ChatSession
from app.services.agent.gateway.router import gateway_router
from app.services.agent.message_store import count_messages, list_session_messages, save_message
from app.services.agent.stream_runner import stream_tool_loop
from app.services.agent.tool_audit import (
    MAX_TOOL_ROUNDS,
    build_assistant_tool_calls,
    build_tool_specs,
    execute_tool_calls,
    parse_text_tool_calls,
    strip_text_tool_calls,
)
from app.core.defaults import DEFAULT_AGENT_MODEL

logger = logging.getLogger("v2.agent.chat")
_cancel_events: dict[int, asyncio.Event] = {}


class ChatService:
    async def get_session_messages(
        self,
        db: AsyncSession,
        session_id: int,
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        return await list_session_messages(db, session_id, page, page_size)

    def build_context(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        max_messages: int = 50,
    ) -> list[dict]:
        base = system_prompt or "You are a helpful AI assistant."
        instructions = (
            "\n\nYou have access to knowledge base tools. When a user asks about specific information, "
            "ALWAYS use the search_knowledge tool to look it up first. "
            "Pass short focused keywords (2-5 Chinese characters) as the query, not the full question. "
            "After receiving tool results, use the data to answer accurately. "
            "When you use search results, cite the source with [^fusion_id]. "
            "Example: user asks '清颜系列有哪些产品', call search_knowledge with query='清颜'."
        )
        ctx = [{"role": "system", "content": base + instructions}]
        ctx.extend({"role": msg.role, "content": msg.content} for msg in messages[-max_messages:])
        return ctx

    async def _load_context(
        self,
        db: AsyncSession,
        session: ChatSession,
    ) -> list[dict]:
        rows = await db.execute(
            select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.id)
        )
        return self.build_context(rows.scalars().all(), session.system_prompt)

    async def send_message(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        content: str,
        profile_key: str = DEFAULT_AGENT_MODEL,
    ) -> dict:
        session = await db.get(ChatSession, session_id)
        if not session or session.user_id != user_id:
            return {"success": False, "error": "Session not found"}
        await save_message(db, session_id, "user", content)
        ctx = await self._load_context(db, session)
        reply, thinking, tools_called = await self._run_tool_loop(ctx, user_id, profile_key)
        saved = await save_message(db, session_id, "assistant", reply, thinking, tools_called=tools_called or None)
        session.message_count = await count_messages(db, session_id)
        await db.commit()
        return {"success": True, "data": {
            "id": saved.id, "role": "assistant", "content": reply,
            "thinking": thinking, "tools_called": tools_called or None,
        }}

    async def _run_tool_loop(
        self,
        ctx: list[dict],
        user_id: int,
        profile_key: str,
    ) -> tuple[str, str, list[dict]]:
        tools_called: list[dict] = []
        final_reply = ""
        final_thinking = ""
        for round_idx in range(MAX_TOOL_ROUNDS):
            result = await gateway_router.chat(ctx, profile_key, tools=build_tool_specs())
            if "error" in result:
                return result.get("content", ""), "", tools_called
            reply = result.get("content", "")
            final_thinking = result.get("thinking", "")
            tool_calls = result.get("tool_calls", []) or parse_text_tool_calls(reply)
            if not tool_calls:
                return reply, final_thinking, tools_called
            logger.info("Tool round %d: calling %d tool(s)", round_idx, len(tool_calls))
            ctx.append({
                "role": "assistant",
                "content": strip_text_tool_calls(reply),
                "tool_calls": build_assistant_tool_calls(tool_calls),
            })
            tools_called.extend(await execute_tool_calls(user_id, tool_calls, ctx))
        return final_reply or "(Agent reached max tool call rounds)", final_thinking, tools_called

    async def stream_message(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        content: str,
        profile_key: str = DEFAULT_AGENT_MODEL,
    ) -> AsyncGenerator[str, None]:
        session = await db.get(ChatSession, session_id)
        if not session or session.user_id != user_id:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Session not found'})}\n\n"
            return
        await save_message(db, session_id, "user", content)
        ctx = await self._load_context(db, session)
        _cancel_events[session_id] = asyncio.Event()
        state: dict = {"reply": "", "thinking": "", "tools_called": []}
        try:
            async for event in stream_tool_loop(ctx, user_id, profile_key, _cancel_events[session_id], state):
                yield event
        finally:
            _cancel_events.pop(session_id, None)
        if state["reply"]:
            await save_message(
                db, session_id, "assistant", state["reply"], state["thinking"],
                tools_called=state["tools_called"] or None,
            )
        session.message_count = await count_messages(db, session_id)
        await db.commit()

    def cancel_stream(self, session_id: int) -> None:
        event = _cancel_events.get(session_id)
        if event:
            event.set()


chat_service = ChatService()
