from sqlalchemy import String, Integer, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base, TimestampMixin


class PromptCategory(Base, TimestampMixin):
    __tablename__ = "framework_prompt_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, comment="Category name")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class PromptTemplate(Base, TimestampMixin):
    __tablename__ = "framework_prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("framework_prompt_categories.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, comment="Template name")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="Prompt content with {{variable}} placeholders")
    variables: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="JSON array of variable names")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, comment="Mark as default template")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="Soft enable/disable")
