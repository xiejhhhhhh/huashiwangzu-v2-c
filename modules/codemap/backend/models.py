"""Codemap 模块自己的表。表名 codemap_ 前缀，不加外键到框架表。"""
from app.models.base import Base, TimestampMixin
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class CodemapFeedback(Base, TimestampMixin):
    """Agent 实读验证后发现 codemap 不准时的反馈记录。"""
    __tablename__ = "codemap_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    query_type: Mapped[str] = mapped_column(String(32), nullable=False)
    codemap_said: Mapped[str] = mapped_column(Text, default="")
    actual: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    agent_id: Mapped[str] = mapped_column(String(128), default="")
