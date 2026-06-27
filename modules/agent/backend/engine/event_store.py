"""事件溯源基座：append-only 事件日志 + 投影成消息。"""
import json
import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import AgentEvent
logger = logging.getLogger("v2.agent").getChild("engine.event_store")
MAX_PAYLOAD_CONTENT_LENGTH = 50000


def _ensure_string_arguments(args: dict | str) -> str:
    """Ensure tool_call ``arguments`` is a JSON string, not a dict/object.

    DeepSeek, Ollama, and most OpenAI-compatible providers require
    ``tool_calls[].function.arguments`` to be a JSON-encoded string.
    The internal unified format keeps it as a dict; this helper converts
    it back to a string when reconstructing messages for the model API.
    Idempotent — passing a string returns it unchanged.
    """
    if isinstance(args, str):
        return args
    try:
        return json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(args)


def _normalize_message_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except Exception:
        return str(content)


async def record_event(
    db: AsyncSession,
    conversation_id: int,
    event_type: str,
    payload: dict,
    llm_response_id: str | None = None,
) -> AgentEvent:
    if not isinstance(payload, dict):
        payload = {"content": str(payload)}
    # Trim oversized payload content to avoid DB bloat
    if "content" in payload and isinstance(payload["content"], str) and len(payload["content"]) > MAX_PAYLOAD_CONTENT_LENGTH:
        payload = {**payload, "content": payload["content"][:MAX_PAYLOAD_CONTENT_LENGTH] + "...(truncated)"}
    if "result" in payload and isinstance(payload["result"], dict):
        result_str = json.dumps(payload["result"], ensure_ascii=False, default=str)
        if len(result_str) > MAX_PAYLOAD_CONTENT_LENGTH:
            payload["result"] = {"_truncated": True, "_preview": result_str[:MAX_PAYLOAD_CONTENT_LENGTH]}
    # Sanitize entire payload: convert non-serializable objects (datetime, etc.) to string
    if payload:
        payload = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    event = AgentEvent(
        conversation_id=conversation_id,
        event_type=event_type,
        payload=payload,
        llm_response_id=llm_response_id,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def read_events(db: AsyncSession, conversation_id: int) -> list[AgentEvent]:
    r = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.conversation_id == conversation_id)
        .order_by(AgentEvent.id)
    )
    return list(r.scalars().all())


async def project_to_messages(
    db: AsyncSession,
    conversation_id: int,
    until_event_id: int | None = None,
) -> list[dict]:
    r = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.conversation_id == conversation_id)
        .order_by(AgentEvent.id)
    )
    all_events = list(r.scalars().all())
    # Handle compaction: collect skipped event ids
    skipped_ids: set[int] = set()
    compaction_summaries: list[dict] = []
    for ev in all_events:
        if ev.event_type == "compaction":
            folded_ids = ev.payload.get("folded_event_ids", [])
            skipped_ids.update(folded_ids)
            compaction_summaries.append({
                "role": "system",
                "content": "[历史摘要] " + ev.payload.get("summary", ""),
            })
    visible = [ev for ev in all_events if ev.id not in skipped_ids]
    messages: list[dict] = []
    i = 0
    while i < len(visible):
        ev = visible[i]
        if ev.event_type == "user_msg":
            messages.append({"role": "user", "content": ev.payload.get("content", "")})
            i += 1
        elif ev.event_type == "assistant_msg":
            if ev.llm_response_id:
                tool_calls = []
                j = i + 1
                tc_ids: set[str] = set()
                while j < len(visible) and visible[j].llm_response_id == ev.llm_response_id and visible[j].event_type == "tool_call":
                    tc_payload = visible[j].payload
                    tc_id = tc_payload.get("id", f"call_{visible[j].id}")
                    tc_ids.add(tc_id)
                    tool_calls.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": tc_payload.get("name", ""),
                            "arguments": _ensure_string_arguments(tc_payload.get("arguments", "{}")),
                        },
                    })
                    j += 1
                # Match tool_result events by tool_call_id (not llm_response_id,
                # because tool_result events store llm_response_id=None).
                k = j
                found_any = False
                while k < len(visible) and visible[k].event_type == "tool_result" and visible[k].payload.get("tool_call_id", "") in tc_ids:
                    k += 1
                    found_any = True
                if found_any:
                    msg = {"role": "assistant", "content": _normalize_message_content(ev.payload.get("content", ""))}
                    msg["tool_calls"] = tool_calls
                    messages.append(msg)
                    for idx in range(j, k):
                        tr_payload = visible[idx].payload
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tr_payload.get("tool_call_id", ""),
                            "content": json.dumps(tr_payload.get("result", {}), ensure_ascii=False),
                        })
                    i = k
                else:
                    # Orphaned tool_calls (e.g. from diminishing_stop):
                    # emit assistant message without tool_calls
                    messages.append({"role": "assistant", "content": _normalize_message_content(ev.payload.get("content", ""))})
                    i = j
            else:
                messages.append({"role": "assistant", "content": _normalize_message_content(ev.payload.get("content", ""))})
                i += 1
        elif ev.event_type == "tool_call":
            # Standalone tool_call — look ahead for matching tool_result
            tc_payload = ev.payload
            tc_id = tc_payload.get("id", f"call_{ev.id}")
            j = i + 1
            found_matching = False
            while j < len(visible) and visible[j].event_type == "tool_result" and visible[j].payload.get("tool_call_id", "") == tc_id:
                found_matching = True
                break
            if found_matching:
                tr_payload = visible[j].payload
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": tc_payload.get("name", ""),
                            "arguments": _ensure_string_arguments(tc_payload.get("arguments", "{}")),
                        },
                    }],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tr_payload.get("tool_call_id", ""),
                    "content": json.dumps(tr_payload.get("result", {}), ensure_ascii=False),
                })
                i = j + 1
            else:
                # Orphaned — skip
                i += 1
        elif ev.event_type == "tool_result":
            # Standalone tool_result — attach to last assistant if it has no tool_calls
            prev = messages[-1] if messages else None
            if prev and prev["role"] == "assistant" and not prev.get("tool_calls"):
                tr_payload = ev.payload
                messages.append({
                    "role": "tool",
                    "tool_call_id": tr_payload.get("tool_call_id", ""),
                    "content": json.dumps(tr_payload.get("result", {}), ensure_ascii=False),
                })
            i += 1
        elif ev.event_type == "memory_op":
            i += 1
        else:
            i += 1
    if compaction_summaries:
        messages = compaction_summaries + messages
    return messages


async def run_event_migration(db: AsyncSession) -> None:
    from sqlalchemy import text
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_events ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  conversation_id BIGINT NOT NULL,"
            "  event_type VARCHAR(32) NOT NULL,"
            "  payload JSONB DEFAULT '{}'::jsonb,"
            "  llm_response_id VARCHAR(64),"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agent_events_conversation_id ON agent_events(conversation_id)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_events table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: agent_events table check failed: %s", e)


async def delete_events_after(db: AsyncSession, conversation_id: int, after_created_at: object, inclusive: bool = False) -> None:
    """Delete events for *conversation_id* with created_at >= (or >) *after_created_at*."""
    from sqlalchemy import delete
    from ..models import AgentEvent
    condition = AgentEvent.created_at >= after_created_at if inclusive else AgentEvent.created_at > after_created_at
    await db.execute(
        delete(AgentEvent).where(
            AgentEvent.conversation_id == conversation_id,
            condition,
        )
    )
