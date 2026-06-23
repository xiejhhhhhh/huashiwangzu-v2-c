"""Memory module models. memory_ prefix."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, Float, Integer, String, Text, DateTime, BigInteger, func as sa_func, text as sa_text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin
from pgvector.sqlalchemy import Vector


class MemoryRecord(Base):
    __tablename__ = "memory_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, comment="原始层：完整记忆文本")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="总结层：LLM 预蒸馏摘要")
    tags: Mapped[str | None] = mapped_column(String(256), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True, comment="bge-m3 1024维向量")
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default=sa_text("1.0"), comment="置信度 0-1")
    recency_score: Mapped[float] = mapped_column(Float, default=1.0, server_default=sa_text("1.0"), comment="时效分，dream 衰减用")
    raw_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="原始层记录 id，下钻用")
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="来源对话 id")
    source: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="来源：auto-distill/user-save/rethink")
    memory_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="类型标签：fact/preference/convention/…")
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True, comment="关键词，逗号分隔")
    access_count: Mapped[int] = mapped_column(Integer, default=0, server_default=sa_text("0"), comment="被召回次数")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa_func.now(), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa_func.now(), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MemoryLink(Base, TimestampMixin):
    """记忆链图：跨对话的语义关联边。"""
    __tablename__ = "memory_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="源记忆 id")
    to_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="目标记忆 id")
    relation: Mapped[str] = mapped_column(String(32), nullable=False, default="semantic_related", comment="关系：semantic_related/same_thread/succession")
    weight: Mapped[float] = mapped_column(Float, default=0.5, comment="边权重 0-1")
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="owner 隔离")


class MemoryExperience(Base):
    """经验记忆：成功/失败的解决路径。全局共享。"""
    __tablename__ = "memory_experiences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger_condition: Mapped[str] = mapped_column(Text, nullable=False, comment="触发条件（自然语言描述）")
    trigger_embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True, comment="触发条件的 embedding")
    steps: Mapped[str] = mapped_column(Text, nullable=False, comment="JSON 有序步骤：每步=意图+工具名+关键参数模式")
    tools_used: Mapped[str] = mapped_column(Text, nullable=True, comment="JSON 列表：用到的能力列表")
    success_weight: Mapped[int] = mapped_column(Integer, default=1, server_default=sa_text("1"), comment="成功权重")
    fail_count: Mapped[int] = mapped_column(Integer, default=0, server_default=sa_text("0"), comment="失败次数")
    fail_notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON 列表：什么情况失败了、为什么")
    source_conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="来源对话 id")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa_text("true"), comment="是否启用（dream 可停用低质经验）")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa_func.now(), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa_func.now(), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
