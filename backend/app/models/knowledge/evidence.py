from sqlalchemy import String, Integer, Float, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Evidence(Base, TimestampMixin):
    __tablename__ = "knowledge_evidences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="script/ocr/vision/fusion")
    source_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="ID in the source table")
    catalog_id: Mapped[int] = mapped_column(Integer, ForeignKey("catalogs.id", ondelete="CASCADE"), nullable=False)
    page_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    cross_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    bound_conclusions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
