"""产品运行时新增表(方案07 §19.3-B / §16.3)。

- framework_product_overrides: Product 覆盖配置层。Product 身份/入口/required capabilities
  来自 products/*/product.json,覆盖层只能改 enabled/sort/visibility/允许的 config。
- framework_migration_batches / framework_migration_items: 迁移账本,中断续跑/隔离/对账。
"""
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, DateTime, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProductOverride(Base):
    """framework_product_overrides —— 唯一键 (scope_type, scope_id, product_id)。"""
    __tablename__ = "framework_product_overrides"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="global", comment="global|user")
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="user id 或 0=global")
    enabled: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visibility_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_by: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "product_id", name="uq_product_override_scope"),
        Index("idx_product_override_product", "product_id"),
    )


class MigrationBatch(Base):
    """framework_migration_batches —— 迁移批次账本。"""
    __tablename__ = "framework_migration_batches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    migration_version: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    checkpoint: Mapped[str | None] = mapped_column(Text, nullable=True, comment="续跑游标(owner_id,file_id 等)")
    # planned|running|paused|validated|failed|rolled_back|completed
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="planned", index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (Index("idx_migration_batch_version", "migration_version"),)


class MigrationItem(Base):
    """framework_migration_items —— 迁移单项(隔离/对账/quarantine)。"""
    __tablename__ = "framework_migration_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    migration_version: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # pending|migrated|quarantined|failed
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (
        Index("idx_migration_item_batch", "batch_id"),
        Index("idx_migration_item_target", "target_type", "target_id"),
    )
