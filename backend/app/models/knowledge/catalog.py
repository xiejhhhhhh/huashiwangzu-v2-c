from sqlalchemy import String, Integer, Text, BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Catalog(Base, TimestampMixin):
    __tablename__ = "catalogs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), default="")
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    file_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, comment="MD5 hash for dedup")
    mime_type: Mapped[str] = mapped_column(String(128), default="")
    channel_type: Mapped[str] = mapped_column(String(32), default="auto", comment="ingestion channel: auto/upload/import/api")
    status: Mapped[str] = mapped_column(String(32), default="pending", comment="pending/processing/done/failed")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
