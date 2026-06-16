from sqlalchemy import String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Label(Base, TimestampMixin):
    __tablename__ = "knowledge_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="file/entity/vision")
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="ID of the target")
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    label_category: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="brand/product/effect etc.")
    passed_admission: Mapped[bool] = mapped_column(Boolean, default=False, comment="Admission gate passed")
