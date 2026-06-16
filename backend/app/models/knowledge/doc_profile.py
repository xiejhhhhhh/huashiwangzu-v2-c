from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base, TimestampMixin


class DocProfile(Base, TimestampMixin):
    __tablename__ = "knowledge_doc_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_id: Mapped[int] = mapped_column(Integer, ForeignKey("catalogs.id", ondelete="CASCADE"), unique=True, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="Document topic")
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Material type")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_entities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    core_conclusions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    searchable_phrases: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
