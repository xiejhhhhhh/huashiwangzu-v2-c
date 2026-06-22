"""Agent 模块自己的表。表名 agent_ 前缀，不加外键到框架表。"""
from datetime import datetime, timezone
from sqlalchemy import Boolean, Integer, JSON, String, Text, BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class AgentConversation(Base, TimestampMixin):
    __tablename__ = "agent_conversations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="新对话")
    status: Mapped[str] = mapped_column(String(16), default="active")
    processing: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否有正在执行的后台任务")


class AgentMessage(Base, TimestampMixin):
    __tablename__ = "agent_messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16))  # user/assistant
    content: Mapped[str] = mapped_column(Text, default="")


class AgentMessageMeta(Base, TimestampMixin):
    __tablename__ = "agent_message_meta"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    thinking: Mapped[str] = mapped_column(Text, default="")
    references: Mapped[list] = mapped_column(JSON, default=list)
    tool_events: Mapped[list] = mapped_column(JSON, default=list)
    timeline: Mapped[list] = mapped_column(JSON, default=list)


# ── 三层提示词系统 ──────────────────────────────────────────

class AgentSystemPrompt(Base, TimestampMixin):
    """全局 1 份：Agent 执行边界 / 人格 / 规则，管理员维护。"""
    __tablename__ = "agent_system_prompt"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentEnterprisePrompt(Base, TimestampMixin):
    """全局 1 份：公司知识 / 规则 / 话术，管理员维护。"""
    __tablename__ = "agent_enterprise_prompt"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentUserProfile(Base, TimestampMixin):
    """每用户 1 份：系统自动进化的个人画像（语气、禁忌、关注点、习惯）。"""
    __tablename__ = "agent_user_profile"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    profile_data: Mapped[str] = mapped_column(Text, default="")  # JSON: tone/taboo/focus/habits
    version: Mapped[int] = mapped_column(Integer, default=0)
    evolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    conversation_count: Mapped[int] = mapped_column(Integer, default=0)
