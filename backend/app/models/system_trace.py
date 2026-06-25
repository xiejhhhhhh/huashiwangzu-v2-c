from sqlalchemy import String, Integer, Text, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.models.base import Base, TimestampMixin


class SystemTraceSpan(Base, TimestampMixin):
    __tablename__ = "system_trace_spans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    span_name: Mapped[str] = mapped_column(String(256), nullable=False)
    start_ms: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    span_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="业务元数据（调用方、事件名等）")
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="调用方 user_id（0 = system）")
