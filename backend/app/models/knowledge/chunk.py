from sqlalchemy import String, Integer, Text, BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from app.models.base import Base, TimestampMixin


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_id: Mapped[int] = mapped_column(Integer, ForeignKey("catalogs.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="SHA256 for dedup")
    page_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_offset: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="Char offset in fusion text")
    source_fusion_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("knowledge_page_fusions.id", ondelete="SET NULL"), nullable=True
    )
    embedding: Mapped[Vector] = mapped_column(Vector(1024), nullable=True)
    chunk_meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
