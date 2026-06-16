from sqlalchemy import String, Integer, Text, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base, TimestampMixin


class PageSource(Base, TimestampMixin):
    __tablename__ = "knowledge_page_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_id: Mapped[int] = mapped_column(Integer, ForeignKey("catalogs.id", ondelete="CASCADE"), nullable=False)
    page_num: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="script/ocr/vision/layout")
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="Raw content JSON per source type")
    screenshot_md5: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Screenshot MD5 for dedup")
    verify_status: Mapped[str] = mapped_column(String(16), default="pending", comment="pending/verified/failed")

    __table_args__ = (
        UniqueConstraint("catalog_id", "page_num", "source_type", name="uq_page_source"),
    )


class PageFusion(Base, TimestampMixin):
    __tablename__ = "knowledge_page_fusions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_id: Mapped[int] = mapped_column(Integer, ForeignKey("catalogs.id", ondelete="CASCADE"), nullable=False)
    page_num: Mapped[int] = mapped_column(Integer, nullable=False)
    fusion_text: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Fused body text")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Page summary")
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    labels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    conflicts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("catalog_id", "page_num", name="uq_page_fusion"),
    )
