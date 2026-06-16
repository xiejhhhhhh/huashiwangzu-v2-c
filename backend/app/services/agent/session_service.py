import logging
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system import ChatSession, ChatMessage
from app.core.defaults import DEFAULT_AGENT_MODEL

logger = logging.getLogger("v2.agent.session")


class SessionService:
    async def list_sessions(
        self, db: AsyncSession, user_id: int, page: int = 1, page_size: int = 50
    ) -> dict:
        total = await db.scalar(
            select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
        )
        count_subq = (
            select(ChatMessage.session_id, func.count(ChatMessage.id).label("cnt"))
            .group_by(ChatMessage.session_id)
            .subquery()
        )
        r = await db.execute(
            select(ChatSession, count_subq.c.cnt)
            .outerjoin(count_subq, ChatSession.id == count_subq.c.session_id)
            .where(ChatSession.user_id == user_id)
            .order_by(desc(ChatSession.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        sessions = []
        for s, cnt in r.all():
            sessions.append({
                "id": s.id,
                "title": s.title,
                "model": s.model,
                "messageCount": cnt or 0,
                "createdAt": s.created_at.isoformat() if s.created_at else "",
                "updatedAt": s.updated_at.isoformat() if s.updated_at else "",
            })
        return {"items": sessions, "total": total or 0, "page": page, "pageSize": page_size}

    async def create_session(
        self,
        db: AsyncSession,
        user_id: int,
        title: str = "New Chat",
        model: str = DEFAULT_AGENT_MODEL,
        system_prompt: str | None = None,
    ) -> ChatSession:
        s = ChatSession(title=title, user_id=user_id, model=model, system_prompt=system_prompt)
        db.add(s)
        await db.commit()
        await db.refresh(s)
        return s

    async def get_session(self, db: AsyncSession, user_id: int, session_id: int) -> ChatSession | None:
        r = await db.execute(
            select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        )
        return r.scalar_one_or_none()

    async def delete_session(self, db: AsyncSession, user_id: int, session_id: int) -> bool:
        s = await self.get_session(db, user_id, session_id)
        if not s:
            return False
        await db.delete(s)
        await db.commit()
        return True

    async def update_title(self, db: AsyncSession, user_id: int, session_id: int, title: str) -> bool:
        s = await self.get_session(db, user_id, session_id)
        if not s:
            return False
        s.title = title
        await db.commit()
        return True


session_service = SessionService()
