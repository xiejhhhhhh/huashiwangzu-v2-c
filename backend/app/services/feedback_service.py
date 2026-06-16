import re
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system import Feedback


_SENSITIVE_KEY_PATTERN = r'(APP_KEY|DB_PASSWORD|DB_USERNAME|API_KEY|SECRET_KEY|JWT_SECRET|STRIPE_SECRET|ACCESS_KEY|PRIVATE_KEY|CLIENT_SECRET|AUTH_TOKEN)'


def sanitize_content(content: str) -> str:
    content = re.sub(r'sk-[A-Za-z0-9_-]{20,}', 'sk-***', content)
    content = re.sub(
        rf'{_SENSITIVE_KEY_PATTERN}\s*=\s*[^\s&,;)\'"]+',
        r'\1=***', content, flags=re.IGNORECASE,
    )
    content = re.sub(
        r'\b(token|secret|password|api_key|api_secret|auth_token|access_token|private_key|client_secret)\s*[=:]\s*[^\s&,;)\'"]+',
        r'\1=***', content, flags=re.IGNORECASE,
    )
    return content


async def submit_feedback(
    db: AsyncSession, user_id: int, feedback_type: str,
    content: str, page_url: str = "", user_agent: str = "",
) -> Feedback:
    safe_content = sanitize_content(content)
    fb = Feedback(
        user_id=user_id, feedback_type=feedback_type, content=safe_content,
        page_url=page_url, user_agent=user_agent, status="pending",
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return fb


async def list_feedbacks(
    db: AsyncSession, page: int = 1, page_size: int = 15,
    status: str | None = None, feedback_type: str | None = None,
):
    stmt = select(Feedback).order_by(desc(Feedback.id))
    count_stmt = select(func.count(Feedback.id))
    if status:
        stmt = stmt.where(Feedback.status == status)
        count_stmt = count_stmt.where(Feedback.status == status)
    if feedback_type:
        stmt = stmt.where(Feedback.feedback_type == feedback_type)
        count_stmt = count_stmt.where(Feedback.feedback_type == feedback_type)
    total = await db.scalar(count_stmt)
    r = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    items = r.scalars().all()
    for fb in items:
        fb.content = sanitize_content(fb.content)
        if fb.admin_note:
            fb.admin_note = sanitize_content(fb.admin_note)
    return items, total or 0


async def get_feedback_detail(db: AsyncSession, feedback_id: int) -> Feedback | None:
    fb = await db.get(Feedback, feedback_id)
    if not fb:
        return None
    fb.content = sanitize_content(fb.content)
    if fb.admin_note:
        fb.admin_note = sanitize_content(fb.admin_note)
    return fb


async def update_feedback_status(
    db: AsyncSession, feedback_id: int, status: str,
    admin_note: str | None, handler_id: int,
) -> Feedback | None:
    fb = await db.get(Feedback, feedback_id)
    if not fb:
        return None
    fb.status = status
    fb.handler_id = handler_id
    fb.handled_at = func.now()
    if admin_note is not None:
        fb.admin_note = admin_note
    await db.commit()
    await db.refresh(fb)
    return fb
