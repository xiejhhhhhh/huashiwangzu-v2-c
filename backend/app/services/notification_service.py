from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system import Notification, UserNotificationRead
from app.core.exceptions import NotFound


async def get_published_notifications(db: AsyncSession, user_id: int, page: int = 1, page_size: int = 20):
    stmt = select(Notification).where(Notification.status == "published").order_by(desc(Notification.published_at))
    total = await db.scalar(select(func.count(Notification.id)).where(Notification.status == "published"))
    r = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    items = r.scalars().all()
    read_ids = set()
    if items:
        nids = [n.id for n in items]
        read_r = await db.execute(
            select(UserNotificationRead.notification_id).where(
                UserNotificationRead.user_id == user_id,
                UserNotificationRead.notification_id.in_(nids),
            )
        )
        read_ids = {row[0] for row in read_r}
    result = []
    for n in items:
        d = {
            "id": n.id, "title": n.title, "content": n.content,
            "notification_type": n.notification_type, "status": n.status,
            "publisher_id": n.publisher_id, "published_at": n.published_at,
            "created_at": n.created_at, "is_read": n.id in read_ids,
        }
        result.append(d)
    return result, total or 0


async def get_unread_count(db: AsyncSession, user_id: int):
    total = await db.scalar(select(func.count(Notification.id)).where(Notification.status == "published"))
    read_count = await db.scalar(
        select(func.count(UserNotificationRead.id)).where(UserNotificationRead.user_id == user_id)
    )
    return max(0, (total or 0) - (read_count or 0))


async def mark_as_read(db: AsyncSession, notification_id: int, user_id: int):
    n = await db.get(Notification, notification_id)
    if not n or n.status != "published":
        raise NotFound("Notification not found")
    existing = await db.execute(
        select(UserNotificationRead).where(
            UserNotificationRead.notification_id == notification_id,
            UserNotificationRead.user_id == user_id,
        )
    )
    if not existing.scalar_one_or_none():
        db.add(UserNotificationRead(notification_id=notification_id, user_id=user_id, read_at=func.now()))
        await db.commit()


async def mark_all_as_read(db: AsyncSession, user_id: int):
    r = await db.execute(select(Notification.id).where(Notification.status == "published"))
    all_ids = [row[0] for row in r]
    if not all_ids:
        return
    existing_r = await db.execute(
        select(UserNotificationRead.notification_id).where(
            UserNotificationRead.user_id == user_id,
            UserNotificationRead.notification_id.in_(all_ids),
        )
    )
    existing_ids = {row[0] for row in existing_r}
    for nid in all_ids:
        if nid not in existing_ids:
            db.add(UserNotificationRead(notification_id=nid, user_id=user_id, read_at=func.now()))
    await db.commit()


async def get_all_announcements(db: AsyncSession, status: str | None = None):
    stmt = select(Notification).order_by(desc(Notification.id))
    if status:
        stmt = stmt.where(Notification.status == status)
    r = await db.execute(stmt)
    return r.scalars().all()


async def create_announcement(db: AsyncSession, title: str, content: str, notification_type: str, publisher_id: int):
    n = Notification(
        title=title, content=content, notification_type=notification_type,
        publisher_id=publisher_id, status="published", published_at=func.now(),
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


async def revoke_announcement(db: AsyncSession, notification_id: int):
    n = await db.get(Notification, notification_id)
    if not n:
        raise NotFound("Notification not found")
    n.status = "revoked"
    await db.commit()
    return n
