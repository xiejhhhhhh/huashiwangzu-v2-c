from sqlalchemy import String, Integer, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base, TimestampMixin


class ExtractCandidate(Base, TimestampMixin):
    __tablename__ = "knowledge_extract_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="Candidate content / value")
    source: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="Source description")
    evidence_page: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="Source page info")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verdict_status: Mapped[int] = mapped_column(Integer, default=0, comment="0=pending/1=confirmed/2=ignored/3=archived")
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class DisambigCandidate(Base, TimestampMixin):
    __tablename__ = "knowledge_disambig_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False)
    entity_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False)
    cooccurrence: Mapped[int] = mapped_column(Integer, default=0, comment="Co-occurrence frequency")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    review_status: Mapped[str] = mapped_column(String(16), default="pending", comment="pending/approved/rejected")
