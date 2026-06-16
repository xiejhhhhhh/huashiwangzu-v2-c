from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class SemanticRole(Base, TimestampMixin):
    __tablename__ = "knowledge_semantic_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True)
    fusion_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("knowledge_page_fusions.id", ondelete="SET NULL"), nullable=True)
    role_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="e.g. subject/predicate/object")
    role_value: Mapped[str] = mapped_column(Text, nullable=False, comment="Role text value")
