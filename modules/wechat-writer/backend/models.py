"""DB models for wechat-writer module."""

from datetime import datetime, timezone

from app.models.base import Base
from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text, text


class WechatDraft(Base):
    __tablename__ = "wechat_drafts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, nullable=False, index=True)
    title = Column(String(500), nullable=False, default="")
    outline = Column(JSON, nullable=True)
    content = Column(Text, nullable=True, default="")
    article_type = Column(String(100), nullable=True, default="")
    keywords = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True, default="")
    status = Column(String(20), nullable=False, default="draft")
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=datetime.now(timezone.utc))
    deleted = Column(Boolean, nullable=False, default=False)


class WechatPrompt(Base):
    __tablename__ = "wechat_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, nullable=False, index=True)
    key = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False, default="")
    content = Column(Text, nullable=False)
    description = Column(Text, nullable=True, default="")
    category = Column(String(50), nullable=True, default="system")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=datetime.now(timezone.utc))
    deleted = Column(Boolean, nullable=False, default=False)
