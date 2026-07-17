"""内容运行时 V1 扩张期：新增 8 表 + 现有框架表可空字段 + 非唯一索引。

Revision ID: a1b2c3d4e5f6
Revises: 7f1a2b3c4d5e
Create Date: 2026-07-17 18:05:00.000000

混合迁移方式（华哥 2026-07-17 定）：新表既有 SQLAlchemy 模型（启动 create_all/patcher 建），
本迁移复用 content_runtime_schema 的同一份定义（不手抄 DDL），保证生产可审计、可 downgrade。
只做扩张期：新表 + 可空字段 + 非唯一索引。所有唯一/NOT NULL 约束切换留 finalize 期迁移。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "7f1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.models.base import Base
    from app.models import content_runtime as _cr  # noqa: F401  触发模型注册
    from app.models import product_runtime as _pr  # noqa: F401
    from app.services.content_runtime_schema import (
        _COLUMN_ADDS,
        _INDEX_ADDS,
        _NEW_TABLE_NAMES,
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1) 新表：用模型定义 checkfirst 建（复用 metadata，不手抄列）
    tables = [Base.metadata.tables[n] for n in _NEW_TABLE_NAMES if n in Base.metadata.tables]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    # 2) 现有框架表加可空字段（存在则跳过）
    for table, column, ddl in _COLUMN_ADDS:
        cols = {c["name"] for c in inspector.get_columns(table)} if table in inspector.get_table_names() else set()
        if column in cols:
            continue
        op.execute(ddl)

    # 3) 非唯一索引（存在则跳过）
    existing_indexes = set()
    for tbl in {t for t, _, _ in _COLUMN_ADDS} | set(_NEW_TABLE_NAMES) | {"framework_content_packages", "framework_content_package_versions"}:
        if tbl in inspector.get_table_names():
            existing_indexes |= {ix["name"] for ix in inspector.get_indexes(tbl)}
    for index_name, ddl in _INDEX_ADDS:
        if index_name in existing_indexes:
            continue
        op.execute(ddl)


def downgrade() -> None:
    """扩张期可回退：删非唯一索引 + 删加的字段 + 删 8 张新表。

    注意：downgrade 只在无回填数据的空环境用于验证；生产回滚以物理备份为准（华哥 2026-07-17 定的兜底）。
    """
    from app.services.content_runtime_schema import (
        _COLUMN_ADDS,
        _INDEX_ADDS,
        _NEW_TABLE_NAMES,
    )

    for index_name, _ in _INDEX_ADDS:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")

    for table, column, _ in _COLUMN_ADDS:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")

    # 先删有外键依赖的子表，再删父表
    for name in ("framework_migration_items", "framework_migration_batches",
                 "framework_product_overrides", "framework_resource_analyses",
                 "framework_content_edit_leases", "framework_event_deliveries",
                 "framework_ingestion_runs", "framework_file_revisions"):
        op.execute(f"DROP TABLE IF EXISTS {name} CASCADE")
