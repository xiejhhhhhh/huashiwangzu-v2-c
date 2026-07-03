"""IM 模块自己的表。im_ 前缀，不加外键。"""
from datetime import datetime, timezone

from app.models.base import Base, TimestampMixin
from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class ImConversation(Base, TimestampMixin):
    __tablename__ = "im_conversations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conv_type: Mapped[str] = mapped_column(String(16), default="single")  # single / group
    creator_id: Mapped[int] = mapped_column(Integer, nullable=False)
    member_ids: Mapped[list] = mapped_column(JSON, default=list)
    last_message_summary: Mapped[str] = mapped_column(String(256), default="")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImMessage(Base, TimestampMixin):
    __tablename__ = "im_messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_id: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    msg_type: Mapped[str] = mapped_column(String(16), default="text")  # text / notification
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ImReadState(Base, TimestampMixin):
    __tablename__ = "im_read_state"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_read_message_id: Mapped[int] = mapped_column(BigInteger, default=0)
