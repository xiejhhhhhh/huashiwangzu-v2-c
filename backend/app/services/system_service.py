from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system import SystemLog, Task, ChatSession, ChatMessage
from app.models.file import File, Folder
from app.models.user import User


async def get_dashboard_stats(db: AsyncSession):
    fcount = await db.scalar(select(func.count(File.id)).where(File.deleted == False))
    focount = await db.scalar(select(func.count(Folder.id)))
    ucount = await db.scalar(select(func.count(User.id)))
    tcount = await db.scalar(select(func.count(Task.id)).where(Task.status == "pending"))
    chcount = await db.scalar(select(func.count(ChatMessage.id)))
    lcount = await db.scalar(select(func.count(SystemLog.id)))
    return {"total_files": fcount or 0, "total_folders": focount or 0, "total_users": ucount or 0,
            "pending_tasks": tcount or 0, "total_chunks": chcount or 0, "total_logs": lcount or 0}


async def create_log(db: AsyncSession, level, module, action, message, user_id=0, ip="", data=None, dur=0):
    db.add(SystemLog(level=level, module=module, action=action, message=message,
                     user_id=user_id or 0, ip_address=ip, request_data=data, duration_ms=dur))
    await db.commit()


async def get_logs(db: AsyncSession, page=1, size=50):
    r = await db.execute(select(SystemLog).order_by(desc(SystemLog.id)).offset((page-1)*size).limit(size))
    return r.scalars().all()


async def get_tasks(db: AsyncSession, user_id: int):
    r = await db.execute(select(Task).where(
        (Task.assignee_id == user_id) | (Task.creator_id == user_id)
    ).order_by(desc(Task.id)))
    return r.scalars().all()


async def create_chat_session(db: AsyncSession, user_id: int, title="New Chat"):
    s = ChatSession(title=title, user_id=user_id)
    db.add(s); await db.commit(); await db.refresh(s); return s


async def get_chat_sessions(db: AsyncSession, user_id: int):
    r = await db.execute(select(ChatSession).where(ChatSession.user_id == user_id).order_by(desc(ChatSession.id)))
    return r.scalars().all()


async def get_chat_messages(db: AsyncSession, session_id: int):
    r = await db.execute(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id))
    return r.scalars().all()
