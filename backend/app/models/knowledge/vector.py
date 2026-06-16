from sqlalchemy import String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.models.base import Base, TimestampMixin


class ChunkVector(Base, TimestampMixin):
    __tablename__ = "knowledge_chunk_vectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[int] = mapped_column(Integer, ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False)
    embedding: Mapped[Vector] = mapped_column(Vector(1024), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, comment="e.g. bge-m3-v1")
    dim: Mapped[int] = mapped_column(Integer, default=1024)
    normalized: Mapped[bool] = mapped_column(Boolean, default=True)
