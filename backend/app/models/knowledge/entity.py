from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base, TimestampMixin


class Entity(Base, TimestampMixin):
    __tablename__ = "knowledge_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    standard_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="Canonical entity name")
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="brand/product/ingredient/effect/organization")
    confirm_status: Mapped[str] = mapped_column(String(16), default="pending", comment="confirmed/pending/rejected")
    pinyin: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="Pinyin for fuzzy matching")
    occurrence_count: Mapped[int] = mapped_column(Integer, default=0)


class EntityAlias(Base, TimestampMixin):
    __tablename__ = "knowledge_entity_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[int] = mapped_column(Integer, ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(256), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), default="synonym", comment="synonym/abbreviation/typo/legacy")


class EntityMerge(Base, TimestampMixin):
    __tablename__ = "knowledge_entity_merges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_entity_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("knowledge_entities.id", ondelete="SET NULL"), nullable=True)
    to_entity_id: Mapped[int] = mapped_column(Integer, ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reverse_map: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Reverse mapping for rollback")
    merged_at: Mapped[str] = mapped_column(String(32), comment="ISO timestamp or version")
