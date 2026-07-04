from app.models.base import Base, TimestampMixin
from sqlalchemy import BigInteger, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class AgentPrompt(Base, TimestampMixin):
    __tablename__ = "agent_prompts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key: Mapped[str] = mapped_column(String(128), default="", index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), default="user")
    is_read_only: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
