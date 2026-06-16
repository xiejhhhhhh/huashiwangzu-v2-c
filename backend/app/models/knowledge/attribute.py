from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base, TimestampMixin


class Attribute(Base, TimestampMixin):
    __tablename__ = "knowledge_attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(256), nullable=False, comment="Subject entity or concept")
    attr_name: Mapped[str] = mapped_column(String(128), nullable=False)
    attr_value: Mapped[str] = mapped_column(Text, nullable=False)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    vote_status: Mapped[str] = mapped_column(String(16), default="unvoted", comment="unvoted/confirmed/rejected/conflict")
