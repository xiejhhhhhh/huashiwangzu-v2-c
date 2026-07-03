import logging
from datetime import datetime, timezone

from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends, Query
from huashiwangzu_modules.im.init_db import run_init
from huashiwangzu_modules.im.models import ImConversation, ImMessage, ImReadState
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.im").getChild("router")

router = APIRouter(prefix="/api/im", tags=["im"])

MAX_MESSAGE_PAGE_SIZE = 100
MAX_MESSAGE_CONTENT_LENGTH = 4000


class SendMessageRequest(BaseModel):
    conversation_id: int | None = Field(default=None, gt=0)
    target_user_id: int | None = Field(default=None, gt=0)
    content: str = Field(..., max_length=MAX_MESSAGE_CONTENT_LENGTH)


class StartConversationRequest(BaseModel):
    target_user_id: int = Field(..., gt=0)


class MarkReadRequest(BaseModel):
    last_read_message_id: int = Field(..., ge=0)


def _parse_user_id(caller: str) -> int:
    if caller and caller.startswith("user:"):
        try:
            return int(caller.split(":", 1)[1])
        except ValueError:
            return 0
    return 0


async def _get_or_create_conversation(db: AsyncSession, user_a: int, user_b: int) -> ImConversation:
    """查找或创建两用户间的单聊会话。"""
    if user_a == user_b:
        raise ValidationError("不能给自己发消息")
    if user_a < 0 or user_b < 0:
        raise ValidationError("用户ID无效")
    stmt = select(ImConversation).where(ImConversation.conv_type == "single")
    r = await db.execute(stmt)
    existing = r.scalars().all()
    for conv in existing:
        members = _conversation_members(conv)
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


def _conversation_members(conv: ImConversation) -> list[int]:
    if not isinstance(conv.member_ids, list):
        return []
    members = []
    for member_id in conv.member_ids:
        try:
            members.append(int(member_id))
        except (TypeError, ValueError):
            continue
    return members


def _message_to_dict(msg: ImMessage) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender_id": msg.sender_id,
        "content": msg.content,
        "msg_type": msg.msg_type,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def _normalize_message_content(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        raise ValidationError("消息内容不能为空")
    if len(normalized) > MAX_MESSAGE_CONTENT_LENGTH:
        raise ValidationError(f"消息内容不能超过 {MAX_MESSAGE_CONTENT_LENGTH} 个字符")
    return normalized


def _content_param(params: dict) -> str:
    content = params.get("content")
    if not isinstance(content, str):
        raise ValidationError("content must be a non-empty string")
    return _normalize_message_content(content)


async def _upsert_read_state(
    db: AsyncSession,
    user_id: int,
    conversation_id: int,
    last_read_message_id: int,
) -> None:
    stmt = select(ImReadState).where(
        ImReadState.user_id == user_id,
        ImReadState.conversation_id == conversation_id,
    )
    r = await db.execute(stmt)
    read_state = r.scalar_one_or_none()
    if read_state:
        read_state.last_read_message_id = max(read_state.last_read_message_id, last_read_message_id)
        return
    db.add(ImReadState(
        user_id=user_id,
        conversation_id=conversation_id,
        last_read_message_id=last_read_message_id,
    ))


async def _count_unread_messages(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
    last_read_message_id: int,
) -> int:
    count_stmt = select(func.count()).select_from(ImMessage).where(
        ImMessage.conversation_id == conversation_id,
        ImMessage.id > last_read_message_id,
        ImMessage.sender_id != user_id,
    )
    cr = await db.execute(count_stmt)
    return cr.scalar() or 0


async def _send_text_message_to_conversation(
    db: AsyncSession,
    conversation_id: int,
    sender_id: int,
    content: str,
) -> ImMessage:
    normalized_content = _normalize_message_content(content)
    conv = await db.get(ImConversation, conversation_id)
    if not conv:
        raise NotFound("会话不存在")
    if sender_id not in _conversation_members(conv):
        raise PermissionDenied("无权向该会话发消息")

    msg = ImMessage(
        conversation_id=conversation_id,
        sender_id=sender_id,
        content=normalized_content,
        msg_type="text",
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    await db.flush()
    summary = normalized_content[:50] + ("..." if len(normalized_content) > 50 else "")
    conv.last_message_summary = summary
    conv.last_message_at = datetime.now(timezone.utc)
    await _upsert_read_state(db, sender_id, conversation_id, int(msg.id))
    await db.commit()
    await db.refresh(msg)
    return msg


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
        members = _conversation_members(conv)
        unread = 0
        read_stmt = select(ImReadState).where(
            ImReadState.user_id == current_user.id,
            ImReadState.conversation_id == conv.id,
        )
        rr = await db.execute(read_stmt)
        read_state = rr.scalar_one_or_none()
        last_read = read_state.last_read_message_id if read_state else 0
        unread = await _count_unread_messages(db, conv.id, current_user.id, last_read)
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_MESSAGE_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    conv = await db.get(ImConversation, conv_id)
    if not conv:
        raise NotFound("会话不存在")
    members = _conversation_members(conv)
    if current_user.id not in members:
        raise PermissionDenied("无权访问该会话")
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


@router.post("/conversations")
async def start_conversation(
    req: StartConversationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    conv = await _get_or_create_conversation(db, current_user.id, req.target_user_id)
    return ApiResponse(data={
        "conversation_id": conv.id,
        "conv_type": conv.conv_type,
        "member_ids": _conversation_members(conv),
    })


@router.post("/messages")
async def send_message(
    req: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await run_init(db)
    content = _normalize_message_content(req.content)
    conv_id = req.conversation_id
    if not conv_id and req.target_user_id:
        if req.target_user_id == current_user.id:
            raise ValidationError("不能给自己发消息")
        conv = await _get_or_create_conversation(db, current_user.id, req.target_user_id)
        conv_id = conv.id
    if not conv_id:
        raise ValidationError("需要 conversation_id 或 target_user_id")
    msg = await _send_text_message_to_conversation(
        db,
        int(conv_id),
        current_user.id,
        content,
    )
    return ApiResponse(data=_message_to_dict(msg))


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
        raise NotFound("会话不存在")
    members = _conversation_members(conv)
    if current_user.id not in members:
        raise PermissionDenied("无权操作")
    if req.last_read_message_id > 0:
        msg_stmt = select(ImMessage.id).where(
            ImMessage.id == req.last_read_message_id,
            ImMessage.conversation_id == conv_id,
        )
        msg_result = await db.execute(msg_stmt)
        if msg_result.scalar_one_or_none() is None:
            raise ValidationError("last_read_message_id 不属于该会话")
    await _upsert_read_state(db, current_user.id, conv_id, req.last_read_message_id)
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
        total += await _count_unread_messages(db, conv.id, current_user.id, last_read)
    return ApiResponse(data={"unread_count": total})


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    """返回系统内可聊用户列表。"""
    from app.models.user import User as UserModel
    from sqlalchemy import select as sa_select
    stmt = sa_select(UserModel.id, UserModel.username, UserModel.display_name).where(UserModel.enabled.is_(True))
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
    content = _content_param(params)
    title = str(params.get("title", "")).strip()
    try:
        target_user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValidationError("user_id must be a positive integer") from None
    if target_user_id <= 0:
        raise ValidationError("user_id must be a positive integer")
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await run_init(db)
        system_id = 0
        conv = await _get_or_create_conversation(db, system_id, target_user_id)
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
        return {"success": True, "message_id": msg.id, "conversation_id": conv.id}


async def _cap_send(params: dict, caller: str) -> dict:
    """让其他模块通过框架给 IM 用户发消息。参数: conversation_id, content。"""
    conv_id = params.get("conversation_id")
    content = _content_param(params)
    try:
        conversation_id = int(conv_id)
    except (TypeError, ValueError):
        raise ValidationError("conversation_id must be a positive integer") from None
    if conversation_id <= 0:
        raise ValidationError("conversation_id must be a positive integer")
    caller_user_id = _parse_user_id(caller)
    if not caller_user_id:
        raise PermissionDenied("im:send requires a user caller")
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await run_init(db)
        msg = await _send_text_message_to_conversation(
            db,
            conversation_id,
            caller_user_id,
            content,
        )
        return {"success": True, "message_id": msg.id, "conversation_id": msg.conversation_id}


register_capability(
    "im", "notify", _cap_notify,
    description="给指定用户推送一条站内通知/消息",
    brief="推送站内通知",
    parameters={"user_id": "int", "content": "str", "title": "str?"},
    min_role="editor",
)

register_capability(
    "im", "send", _cap_send,
    description="向指定会话发送消息",
    brief="发送站内消息",
    parameters={"conversation_id": "int", "content": "str"},
    min_role="viewer",
)
