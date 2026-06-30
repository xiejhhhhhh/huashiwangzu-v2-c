"""Agent 会话/消息/提示词服务。只碰 agent_ 表。

三层提示词系统：
- 系统提示词（agent_system_prompt）：全局 1 份，管理员维护
- 企业提示词（agent_enterprise_prompt）：全局 1 份，管理员维护
- 个人画像（agent_user_profile）：每用户 1 份，系统自动进化
"""
import json
import logging

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    AgentContextCompaction,
    AgentConversation,
    AgentEnterprisePrompt,
    AgentMessage,
    AgentMessageMeta,
    AgentSystemPrompt,
    AgentUserProfile,
)
from ..prompt_seeds import ENTERPRISE_PROMPT_KEY, SYSTEM_BASE_PROMPT_KEY
from .runtime_prompt_provider import get_system_prompt as get_runtime_system_prompt

logger = logging.getLogger("v2.agent").getChild("conversation_service")

MAX_CONTEXT_MESSAGES = 24

DEFAULT_PROFILE_TEMPLATE = {
    "tone": "",
    "taboos": [],
    "focus": [],
    "habits": [],
}

# ── Conversations ──────────────────────────────────────────

async def list_conversations(db: AsyncSession, owner_id: int) -> list[AgentConversation]:
    r = await db.execute(
        select(AgentConversation)
        .where(AgentConversation.owner_id == owner_id, AgentConversation.status == "active")
        .order_by(desc(AgentConversation.id))
    )
    return list(r.scalars().all())


async def create_conversation(db: AsyncSession, owner_id: int, title: str = "新对话") -> AgentConversation:
    conv = AgentConversation(owner_id=owner_id, title=title, status="active")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def rename_conversation(db: AsyncSession, owner_id: int, conversation_id: int, title: str) -> AgentConversation | None:
    conv = await db.get(AgentConversation, conversation_id)
    if not conv or conv.owner_id != owner_id or conv.status != "active":
        return None
    conv.title = title
    await db.commit()
    await db.refresh(conv)
    return conv


async def delete_conversation(db: AsyncSession, owner_id: int, conversation_id: int) -> bool:
    conv = await db.get(AgentConversation, conversation_id)
    if not conv or conv.owner_id != owner_id or conv.status != "active":
        return False
    conv.status = "deleted"
    await invalidate_context_compactions(db, conversation_id, "invalidated by conversation deletion")
    await db.commit()
    return True


async def invalidate_context_compactions(
    db: AsyncSession,
    conversation_id: int,
    reason: str,
) -> None:
    """Invalidate visible and in-flight snapshots after history mutation."""
    await db.execute(
        update(AgentContextCompaction)
        .where(
            AgentContextCompaction.conversation_id == conversation_id,
            AgentContextCompaction.status.in_(("building", "ready")),
        )
        .values(status="failed", error=reason[:1000])
    )


# ── Messages ───────────────────────────────────────────────

async def get_messages(db: AsyncSession, owner_id: int, conversation_id: int, status: str = "active") -> list[AgentMessage]:
    r = await db.execute(
        select(AgentMessage)
        .where(
            AgentMessage.owner_id == owner_id,
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.status == status,
        )
        .order_by(AgentMessage.id)
    )
    return list(r.scalars().all())


async def add_message(db: AsyncSession, owner_id: int, conversation_id: int, role: str, content: str) -> AgentMessage:
    msg = AgentMessage(owner_id=owner_id, conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def add_message_meta(
    db: AsyncSession,
    owner_id: int,
    conversation_id: int,
    message_id: int,
    thinking: str = "",
    references: list | None = None,
    tool_events: list | None = None,
    timeline: list | None = None,
    usage: dict | None = None,
) -> AgentMessageMeta:
    meta = AgentMessageMeta(
        owner_id=owner_id,
        conversation_id=conversation_id,
        message_id=message_id,
        thinking=thinking,
        references=references or [],
        tool_events=tool_events or [],
            timeline=timeline or [],
            usage=usage or None,
        )

    db.add(meta)
    await db.commit()
    await db.refresh(meta)
    return meta


async def list_message_meta(db: AsyncSession, owner_id: int, conversation_id: int, status: str = "active") -> dict[int, AgentMessageMeta]:
    r = await db.execute(
        select(AgentMessageMeta)
        .where(
            AgentMessageMeta.owner_id == owner_id,
            AgentMessageMeta.conversation_id == conversation_id,
        )
    )
    all_meta = {int(item.message_id): item for item in r.scalars().all()}
    if status:
        active_msg_ids = set(
            m.id for m in await get_messages(db, owner_id, conversation_id, status=status)
        )
        return {k: v for k, v in all_meta.items() if k in active_msg_ids}
    return all_meta


async def get_messages_with_meta(db: AsyncSession, owner_id: int, conversation_id: int) -> list[dict]:
    messages = await get_messages(db, owner_id, conversation_id)
    meta_by_message = await list_message_meta(db, owner_id, conversation_id)
    result: list[dict] = []
    for msg in messages:
        meta = meta_by_message.get(int(msg.id))
        result.append({
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            "thinking": meta.thinking if meta else "",
            "references": meta.references if meta else [],
            "tool_events": meta.tool_events if meta else [],
            "timeline": meta.timeline if meta else [],
            "usage": meta.usage if meta else None,
        })
    return result


async def rollback_conversation(db: AsyncSession, owner_id: int, conversation_id: int, message_id: int) -> bool:
    """Rollback conversation to a specific user message.

    Deletes all messages, meta, and events after the given message_id.
    Returns False if the message doesn't belong to this user/conversation.
    """
    msg = await db.get(AgentMessage, message_id)
    if not msg or msg.conversation_id != conversation_id or msg.owner_id != owner_id:
        return False

    from sqlalchemy import delete

    from ..engine.event_store import delete_events_after

    await db.execute(
        delete(AgentMessageMeta).where(
            AgentMessageMeta.conversation_id == conversation_id,
            AgentMessageMeta.message_id > message_id,
        )
    )
    await db.execute(
        delete(AgentMessage).where(
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.id > message_id,
        )
    )
    await delete_events_after(db, conversation_id, msg.created_at)
    await invalidate_context_compactions(db, conversation_id, "invalidated by rollback")
    await db.commit()
    return True


async def count_conversation_messages(db: AsyncSession, owner_id: int, conversation_id: int) -> int:
    """统计该对话的活跃消息数（用于画像进化节流判断）。"""
    r = await db.execute(
        select(AgentMessage)
        .where(
            AgentMessage.owner_id == owner_id,
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.status == "active",
        )
    )
    rows = r.scalars().all()
    # Count only user+assistant pairs
    user_count = sum(1 for m in rows if m.role == "user")
    return user_count


# ── 编辑重跑（软分支） ─────────────────────────────────────

async def archive_messages_after(db: AsyncSession, conversation_id: int, after_message_id: int) -> list[int]:
    """Mark all messages after *after_message_id* as archived.
    Returns the list of archived message IDs.
    """
    r = await db.execute(
        select(AgentMessage)
        .where(
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.id > after_message_id,
        )
        .order_by(AgentMessage.id)
    )
    tail = list(r.scalars().all())
    archived_ids = []
    for msg in tail:
        msg.status = "archived"
        archived_ids.append(msg.id)
    await db.commit()
    return archived_ids


async def invalidate_checkpoints_after(db: AsyncSession, conversation_id: int) -> None:
    """Delete all checkpoints for the conversation (they reference old messages)."""
    from sqlalchemy import text as _text
    await db.execute(_text(
        "DELETE FROM agent_checkpoints WHERE conversation_id = :conv_id"
    ), {"conv_id": conversation_id})
    await db.commit()


async def edit_and_resubmit(
    db: AsyncSession,
    owner_id: int,
    conversation_id: int,
    message_id: int,
    new_content: str,
) -> AgentMessage | None:
    """Edit a user message content and archive all tail messages.

    Returns the updated AgentMessage, or None on validation failure.

    1. Validates the message belongs to the user/conversation and is role='user'.
    2. Updates the message content to *new_content*.
    3. Archives all messages after this one (status='archived').
    4. Deletes ALL events from this message onward (both the user_msg event
       for this message and all subsequent events) so that context assembly
       projects only pre-edit history + the new content as current input.
    5. Invalidates old checkpoints.
    6. Deletes message_meta for archived messages.
    """
    msg = await db.get(AgentMessage, message_id)
    if not msg or msg.conversation_id != conversation_id or msg.owner_id != owner_id:
        return None
    if msg.role != "user":
        return None
    if not new_content or not new_content.strip():
        return None

    # Mark as branch root if not already
    if not msg.branch_root_message_id:
        msg.branch_root_message_id = message_id

    # Archive tail messages
    archived_ids = await archive_messages_after(db, conversation_id, message_id)

    # Update content
    msg.content = new_content
    await db.commit()
    await db.refresh(msg)

    # Delete ALL events from this message's created_at onward (including
    # the user_msg event for this message) so context assembly sees ONLY
    # history before the edit point + the new content will be the
    # current_input passed by the runtime.
    from ..engine.event_store import delete_events_after
    await delete_events_after(db, conversation_id, msg.created_at, inclusive=True)
    await invalidate_context_compactions(db, conversation_id, "invalidated by edit")

    # Delete message_meta for archived messages
    if archived_ids:
        from sqlalchemy import delete
        await db.execute(
            delete(AgentMessageMeta).where(
                AgentMessageMeta.conversation_id == conversation_id,
                AgentMessageMeta.message_id.in_(archived_ids),
            )
        )
        await db.commit()

    # Invalidate old checkpoints
    await invalidate_checkpoints_after(db, conversation_id)

    return msg


# ── 三层提示词系统 ──────────────────────────────────────────

async def get_system_prompt(db: AsyncSession) -> str:
    """获取当前生效的系统提示词。"""
    prompt = await get_runtime_system_prompt(db, SYSTEM_BASE_PROMPT_KEY)
    if prompt:
        return prompt
    r = await db.execute(
        select(AgentSystemPrompt).order_by(desc(AgentSystemPrompt.id)).limit(1)
    )
    legacy = r.scalar_one_or_none()
    return legacy.content if legacy else ""


async def get_enterprise_prompt(db: AsyncSession) -> str:
    """获取当前生效的企业提示词。"""
    prompt = await get_runtime_system_prompt(db, ENTERPRISE_PROMPT_KEY)
    if prompt:
        return prompt
    r = await db.execute(
        select(AgentEnterprisePrompt).order_by(desc(AgentEnterprisePrompt.id)).limit(1)
    )
    legacy = r.scalar_one_or_none()
    return legacy.content if legacy else ""


async def get_active_user_profile(db: AsyncSession, owner_id: int) -> dict:
    """获取用户的个人画像数据，转为 dict。"""
    r = await db.execute(
        select(AgentUserProfile).where(AgentUserProfile.owner_id == owner_id)
    )
    profile = r.scalar_one_or_none()
    if not profile or not profile.profile_data:
        return dict(DEFAULT_PROFILE_TEMPLATE)
    try:
        data = json.loads(profile.profile_data)
        if isinstance(data, dict):
            return {**DEFAULT_PROFILE_TEMPLATE, **data}
        return dict(DEFAULT_PROFILE_TEMPLATE)
    except (json.JSONDecodeError, TypeError):
        return dict(DEFAULT_PROFILE_TEMPLATE)


def _format_profile_text(profile_data: dict) -> str:
    """把结构化画像转为 system prompt 段落。"""
    parts = []
    tone = profile_data.get("tone", "")
    if tone:
        parts.append(f"语气偏好：{tone}")
    taboos = profile_data.get("taboos", [])
    if taboos:
        parts.append("禁忌话题：" + "、".join(taboos) if isinstance(taboos, list) else f"禁忌：{taboos}")
    focus = profile_data.get("focus", [])
    if focus:
        parts.append("关注领域：" + "、".join(focus) if isinstance(focus, list) else f"关注：{focus}")
    habits = profile_data.get("habits", [])
    if habits:
        parts.append("习惯：\n" + "\n".join(f"- {h}" for h in habits) if isinstance(habits, list) else f"习惯：{habits}")
    if not parts:
        return ""
    return "用户个人画像（系统自动学习）：\n" + "\n".join(parts)


async def build_context_messages(
    db: AsyncSession,
    owner_id: int,
    history: list[AgentMessage],
) -> list[dict]:
    """构建带三层提示词的 context messages。

    system 消息 = 系统提示词 + 企业提示词 + 该用户个人画像，拼接注入。
    """
    sys_prompt = await get_system_prompt(db)
    ent_prompt = await get_enterprise_prompt(db)
    profile_data = await get_active_user_profile(db, owner_id)
    profile_text = _format_profile_text(profile_data)

    # 拼接三层
    layers = []
    if sys_prompt:
        layers.append(sys_prompt)
    if ent_prompt:
        layers.append(ent_prompt)
    if profile_text:
        layers.append(profile_text)

    system_content = "\n\n---\n\n".join(layers)

    recent = history[-MAX_CONTEXT_MESSAGES:]
    messages = [{"role": "system", "content": system_content}]
    if len(history) > len(recent):
        omitted = len(history) - len(recent)
        messages.append({
            "role": "system",
            "content": f"前文已有 {omitted} 条消息被折叠。保留最近上下文继续回答。",
        })
    messages.extend({"role": item.role, "content": item.content} for item in recent)
    return messages


# ── 管理员提示词维护 ────────────────────────────────────────

async def update_system_prompt(db: AsyncSession, content: str, updated_by: int) -> AgentSystemPrompt:
    """管理员更新系统提示词（新版本）。"""
    prompt = AgentSystemPrompt(content=content, version=1, updated_by=updated_by)
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return prompt


async def update_enterprise_prompt(db: AsyncSession, content: str, updated_by: int) -> AgentEnterprisePrompt:
    """管理员更新企业提示词（新版本）。"""
    prompt = AgentEnterprisePrompt(content=content, version=1, updated_by=updated_by)
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return prompt


async def get_user_profile(db: AsyncSession, owner_id: int) -> AgentUserProfile | None:
    """获取用户画像记录。"""
    from ..init_db import ensure_user_profile
    return await ensure_user_profile(db, owner_id)


# ── 画像进化 ────────────────────────────────────────────────

async def update_user_profile(
    db: AsyncSession,
    owner_id: int,
    profile_data: dict,
) -> AgentUserProfile:
    """更新用户画像（版本递增 + 时间戳）。"""
    from datetime import datetime, timezone

    from ..init_db import ensure_user_profile

    profile = await ensure_user_profile(db, owner_id)
    profile.profile_data = json.dumps(profile_data, ensure_ascii=False)
    profile.version = (profile.version or 0) + 1
    profile.evolved_at = datetime.now(timezone.utc)
    profile.conversation_count = (profile.conversation_count or 0) + 1
    await db.commit()
    await db.refresh(profile)
    return profile


async def increment_conversation_count(db: AsyncSession, owner_id: int) -> None:
    """对话完成时递增画像会话计数。"""
    from ..init_db import ensure_user_profile
    profile = await ensure_user_profile(db, owner_id)
    profile.conversation_count = (profile.conversation_count or 0) + 1
    await db.commit()
