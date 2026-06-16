from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import ChatMessage


async def save_message(
    db: AsyncSession,
    session_id: int,
    role: str,
    content: str,
    thinking: str | None = None,
    tokens: int = 0,
    tools_called: list | None = None,
) -> ChatMessage:
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        thinking=thinking,
        tokens=tokens,
        tools_called=tools_called,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def count_messages(db: AsyncSession, session_id: int) -> int:
    total = await db.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
    )
    return total or 0


def serialize_message(msg: ChatMessage) -> dict:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "thinking": msg.thinking,
        "tools_called": msg.tools_called,
        "createdAt": msg.created_at.isoformat() if msg.created_at else "",
    }


async def list_session_messages(
    db: AsyncSession,
    session_id: int,
    page: int = 1,
    page_size: int = 100,
) -> dict:
    total = await db.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
    )
    rows = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [serialize_message(item) for item in rows.scalars().all()],
        "total": total or 0,
        "page": page,
        "pageSize": page_size,
    }
