import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability

logger = logging.getLogger("v2.im.router")

from huashiwangzu_modules.im.models import ImConversation, ImMessage, ImReadState
from huashiwangzu_modules.im.init_db import run_init

router = APIRouter(prefix="/api/im", tags=["im"])


class SendMessageRequest(BaseModel):
    conversation_id: int | None = None
    target_user_id: int | None = None
    content: str


class MarkReadRequest(BaseModel):
    last_read_message_id: int


def _parse_user_id(caller: str) -> int:
    if caller and caller.startswith("user:"):
        return int(caller.split(":", 1)[1])
    return 0


async def _get_or_create_conversation(db: AsyncSession, user_a: int, user_b: int) -> ImConversation:
    """查找或创建两用户间的单聊会话。"""
    stmt = select(ImConversation).where(ImConversation.conv_type == "single")
    r = await db.execute(stmt)
    existing = r.scalars().all()
    for conv in existing:
        members = conv.member_ids if isinstance(conv.member_ids, list) else []
        if user_a in members and user_b in members:
            return conv
    conv = ImConversation(
        conv_type="single",
        creator_id=user_a,
        member_ids=[user_a, user_b],
        last_message_summary="",
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def _ensure_table_init(db: AsyncSession) -> None:
    tables_exist = await db.execute(select(func.count()).select_from(ImConversation.__table__).limit(0))
    if tables_exist is None:
        await run_init(db)


@router.get("/conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    all_stmt = select(ImConversation).order_by(ImConversation.last_message_at.desc().nullslast())
    r = await db.execute(all_stmt)
    all_convs = r.scalars().all()
    convs = [c for c in all_convs if current_user.id in (c.member_ids if isinstance(c.member_ids, list) else [])]

    result = []
    for conv in convs:
        members = conv.member_ids if isinstance(conv.member_ids, list) else []
        unread = 0
        read_stmt = select(ImReadState).where(
            ImReadState.user_id == current_user.id,
            ImReadState.conversation_id == conv.id,
        )
        rr = await db.execute(read_stmt)
        read_state = rr.scalar_one_or_none()
        last_read = read_state.last_read_message_id if read_state else 0
        if last_read > 0:
            count_stmt = select(func.count()).select_from(ImMessage).where(
                ImMessage.conversation_id == conv.id,
                ImMessage.id > last_read,
            )
            cr = await db.execute(count_stmt)
            unread = cr.scalar() or 0
        else:
            count_stmt = select(func.count()).select_from(ImMessage).where(
                ImMessage.conversation_id == conv.id,
            )
            cr = await db.execute(count_stmt)
            total = cr.scalar() or 0
            unread = total
        result.append({
            "id": conv.id,
            "conv_type": conv.conv_type,
            "creator_id": conv.creator_id,
            "member_ids": members,
            "last_message_summary": conv.last_message_summary or "",
            "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
            "unread_count": unread,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        })
    return ApiResponse(data=result)


@router.get("/conversations/{conv_id}/messages")
async def get_messages(
    conv_id: int,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    conv = await db.get(ImConversation, conv_id)
    if not conv:
        return ApiResponse(success=False, error="会话不存在")
    members = conv.member_ids if isinstance(conv.member_ids, list) else []
    if current_user.id not in members:
        return ApiResponse(success=False, error="无权访问该会话")
    offset = max(0, (page - 1) * page_size)
    stmt = select(ImMessage).where(
        ImMessage.conversation_id == conv_id,
    ).order_by(ImMessage.id.desc()).offset(offset).limit(page_size)
    r = await db.execute(stmt)
    msgs = r.scalars().all()
    return ApiResponse(data=[{
        "id": m.id,
        "conversation_id": m.conversation_id,
        "sender_id": m.sender_id,
        "content": m.content,
        "msg_type": m.msg_type,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in reversed(msgs)])


@router.post("/messages")
async def send_message(
    req: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    conv_id = req.conversation_id
    if not conv_id and req.target_user_id:
        if req.target_user_id == current_user.id:
            return ApiResponse(success=False, error="不能给自己发消息")
        conv = await _get_or_create_conversation(db, current_user.id, req.target_user_id)
        conv_id = conv.id
    if not conv_id:
        return ApiResponse(success=False, error="需要 conversation_id 或 target_user_id")
    conv = await db.get(ImConversation, conv_id)
    if not conv:
        return ApiResponse(success=False, error="会话不存在")
    members = conv.member_ids if isinstance(conv.member_ids, list) else []
    if current_user.id not in members:
        return ApiResponse(success=False, error="无权向该会话发消息")
    msg = ImMessage(
        conversation_id=conv_id,
        sender_id=current_user.id,
        content=req.content,
        msg_type="text",
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    summary = req.content[:50] + ("..." if len(req.content) > 50 else "")
    conv.last_message_summary = summary
    conv.last_message_at = datetime.now(timezone.utc)
    await db.commit()
    return ApiResponse(data={
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender_id": msg.sender_id,
        "content": msg.content,
        "msg_type": msg.msg_type,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    })


@router.post("/conversations/{conv_id}/read")
async def mark_read(
    conv_id: int,
    req: MarkReadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    conv = await db.get(ImConversation, conv_id)
    if not conv:
        return ApiResponse(success=False, error="会话不存在")
    members = conv.member_ids if isinstance(conv.member_ids, list) else []
    if current_user.id not in members:
        return ApiResponse(success=False, error="无权操作")
    stmt = select(ImReadState).where(
        ImReadState.user_id == current_user.id,
        ImReadState.conversation_id == conv_id,
    )
    r = await db.execute(stmt)
    rs = r.scalar_one_or_none()
    if rs:
        rs.last_read_message_id = max(rs.last_read_message_id, req.last_read_message_id)
    else:
        rs = ImReadState(
            user_id=current_user.id,
            conversation_id=conv_id,
            last_read_message_id=req.last_read_message_id,
        )
        db.add(rs)
    await db.commit()
    return ApiResponse(data={"status": "ok"})


@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    all_stmt = select(ImConversation)
    r = await db.execute(all_stmt)
    all_convs = r.scalars().all()
    convs = [c for c in all_convs if current_user.id in (c.member_ids if isinstance(c.member_ids, list) else [])]
    total = 0
    for conv in convs:
        read_stmt = select(ImReadState).where(
            ImReadState.user_id == current_user.id,
            ImReadState.conversation_id == conv.id,
        )
        rr = await db.execute(read_stmt)
        rs = rr.scalar_one_or_none()
        last_read = rs.last_read_message_id if rs else 0
        count_stmt = select(func.count()).select_from(ImMessage).where(
            ImMessage.conversation_id == conv.id,
            ImMessage.id > last_read,
        )
        cr = await db.execute(count_stmt)
        total += cr.scalar() or 0
    return ApiResponse(data={"unread_count": total})


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    """返回系统内可聊用户列表。"""
    from app.models.user import User as UserModel
    from sqlalchemy import select as sa_select
    stmt = sa_select(UserModel.id, UserModel.username, UserModel.display_name).where(UserModel.enabled == True)
    r = await db.execute(stmt)
    users = r.all()
    return ApiResponse(data=[{
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name or u.username,
    } for u in users if u.id != current_user.id])


# ── 跨模块能力：im.notify ──────────────────────────────────

async def _cap_notify(params: dict, caller: str) -> dict:
    """给指定用户推送一条站内通知。参数: user_id, content, title(可选)。"""
    user_id = params.get("user_id")
    content = params.get("content", "")
    title = params.get("title", "")
    if not user_id or not content:
        return {"success": False, "error": "user_id and content required"}
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await run_init(db)
        system_id = 0
        conv = await _get_or_create_conversation(db, system_id, int(user_id))
        full_content = f"[{title}] {content}" if title else content
        msg = ImMessage(
            conversation_id=conv.id,
            sender_id=system_id,
            content=full_content,
            msg_type="notification",
            created_at=datetime.now(timezone.utc),
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        summary = full_content[:50] + ("..." if len(full_content) > 50 else "")
        conv.last_message_summary = summary
        conv.last_message_at = datetime.now(timezone.utc)
        await db.commit()
        return {"success": True, "message_id": msg.id}


async def _cap_send(params: dict, caller: str) -> dict:
    """让其他模块通过框架给 IM 用户发消息。参数: conversation_id, content。"""
    conv_id = params.get("conversation_id")
    content = params.get("content", "")
    if not conv_id or not content:
        return {"success": False, "error": "conversation_id and content required"}
    caller_user_id = _parse_user_id(caller)
    if not caller_user_id:
        caller_user_id = params.get("sender_id", 0)
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await run_init(db)
        msg = ImMessage(
            conversation_id=int(conv_id),
            sender_id=caller_user_id,
            content=content,
            msg_type="text",
            created_at=datetime.now(timezone.utc),
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        conv = await db.get(ImConversation, int(conv_id))
        if conv:
            summary = content[:50] + ("..." if len(content) > 50 else "")
            conv.last_message_summary = summary
            conv.last_message_at = datetime.now(timezone.utc)
            await db.commit()
        return {"success": True, "message_id": msg.id}


register_capability(
    "im", "notify", _cap_notify,
    description="给指定用户推送一条站内通知/消息",
    parameters={"user_id": "int", "content": "str", "title": "str?"},
    min_role="editor",
)

register_capability(
    "im", "send", _cap_send,
    description="向指定会话发送消息",
    parameters={"conversation_id": "int", "content": "str"},
    min_role="viewer",
)
