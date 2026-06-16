from sqlalchemy import String, Integer, Text, DateTime, BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class KnowledgeTask(Base, TimestampMixin):
    __tablename__ = "knowledge_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_id: Mapped[int] = mapped_column(Integer, ForeignKey("catalogs.id", ondelete="CASCADE"), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="extract/fuse/chunk/vectorize/candidate/resolve")
    status: Mapped[str] = mapped_column(String(16), default="pending", comment="pending/processing/done/failed")
    lease_until: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="0-100")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
