"""内容运行时 V1 —— 扩张期幂等 DDL（Expand-phase schema patcher）。

混合迁移方式（华哥 2026-07-17 定）：
- 新表既写 SQLAlchemy 模型（dev/启动 create_all 自动建），又由本模块 checkfirst 建（生产可控）。
- 现有框架表加字段用幂等 ALTER TABLE ADD COLUMN IF NOT EXISTS，跟 ensure_framework_scheduling_columns 同套路。
- 本模块只做「扩张期」：新表 + 可空字段 + 非唯一索引。
  所有唯一/NOT NULL 约束切换（hash 唯一改 (owner_id,hash)、resource_refs.version_id 必填、
  content_packages.source_file_id 部分唯一等）一律留到「回填后 finalize 期」，不在此处执行。

模块边界：只碰 framework_* 表。excel_* / kb_documents 的新增字段由各自模块 DDL 负责（模块隔离）。

Alembic 迁移与本函数复用同一份定义：迁移直接 import 调用本函数，不手抄 DDL，避免双份漂移。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 独立 advisory lock key（与 task queue 的 migration lock 不同，避免互相阻塞）
CONTENT_RUNTIME_MIGRATION_LOCK_KEY = 0x00C0_17E5_2026_0717

# 新增框架表（由模型定义，checkfirst 建；顺序无关，create_all 自解依赖）
_NEW_TABLE_NAMES = (
    "framework_file_revisions",
    "framework_ingestion_runs",
    "framework_event_deliveries",
    "framework_content_edit_leases",
    "framework_resource_analyses",
    "framework_product_overrides",
    "framework_migration_batches",
    "framework_migration_items",
)

# 现有框架表新增可空字段（扩张期；不带 NOT NULL、不带唯一）
# 每项: (表名, 列名, ALTER 语句)
_COLUMN_ADDS: tuple[tuple[str, str, str], ...] = (
    # framework_file_items —— 当前 Revision 指针 + 真实字节 sha256
    ("framework_file_items", "current_revision_id",
     "ALTER TABLE framework_file_items ADD COLUMN current_revision_id BIGINT"),
    ("framework_file_items", "sha256_hash",
     "ALTER TABLE framework_file_items ADD COLUMN sha256_hash VARCHAR(64)"),
    # framework_content_packages —— Profile / schema 版本 / 来源 Revision / 活跃 Ingestion
    ("framework_content_packages", "profile",
     "ALTER TABLE framework_content_packages ADD COLUMN profile VARCHAR(32)"),
    ("framework_content_packages", "schema_version",
     "ALTER TABLE framework_content_packages ADD COLUMN schema_version VARCHAR(64)"),
    ("framework_content_packages", "source_revision_id",
     "ALTER TABLE framework_content_packages ADD COLUMN source_revision_id BIGINT"),
    ("framework_content_packages", "active_ingestion_id",
     "ALTER TABLE framework_content_packages ADD COLUMN active_ingestion_id VARCHAR(36)"),
    # framework_content_package_versions —— 父版本 / hash / 保真 / 保留状态（内容/profile/hash/parent 创建后不可改由应用层守，DB 侧先加列）
    ("framework_content_package_versions", "parent_version_id",
     "ALTER TABLE framework_content_package_versions ADD COLUMN parent_version_id BIGINT"),
    ("framework_content_package_versions", "schema_version",
     "ALTER TABLE framework_content_package_versions ADD COLUMN schema_version VARCHAR(64)"),
    ("framework_content_package_versions", "profile",
     "ALTER TABLE framework_content_package_versions ADD COLUMN profile VARCHAR(32)"),
    ("framework_content_package_versions", "content_sha256",
     "ALTER TABLE framework_content_package_versions ADD COLUMN content_sha256 VARCHAR(64)"),
    ("framework_content_package_versions", "source_sha256",
     "ALTER TABLE framework_content_package_versions ADD COLUMN source_sha256 VARCHAR(64)"),
    ("framework_content_package_versions", "fidelity_level",
     "ALTER TABLE framework_content_package_versions ADD COLUMN fidelity_level VARCHAR(16)"),
    ("framework_content_package_versions", "retention_state",
     "ALTER TABLE framework_content_package_versions ADD COLUMN retention_state VARCHAR(16) DEFAULT 'active'"),
    # WP3 双写：CanonicalContentIRV1 载荷（旧 content_json 不动，供 WP7 翻转读者切过来）
    ("framework_content_package_versions", "canonical_json",
     "ALTER TABLE framework_content_package_versions ADD COLUMN canonical_json TEXT"),
    # framework_resource_refs —— 稳定 ref_key（version_id 必填 + 唯一切换留 finalize）
    ("framework_resource_refs", "ref_key",
     "ALTER TABLE framework_resource_refs ADD COLUMN ref_key VARCHAR(128)"),
    # framework_system_task_queues —— 幂等键 + Ingestion 关联 + 版本/hash + 取消
    ("framework_system_task_queues", "idempotency_key",
     "ALTER TABLE framework_system_task_queues ADD COLUMN idempotency_key VARCHAR(255)"),
    ("framework_system_task_queues", "ingestion_id",
     "ALTER TABLE framework_system_task_queues ADD COLUMN ingestion_id VARCHAR(36)"),
    ("framework_system_task_queues", "stage_version",
     "ALTER TABLE framework_system_task_queues ADD COLUMN stage_version VARCHAR(32)"),
    ("framework_system_task_queues", "handler_version",
     "ALTER TABLE framework_system_task_queues ADD COLUMN handler_version VARCHAR(32)"),
    ("framework_system_task_queues", "input_hash",
     "ALTER TABLE framework_system_task_queues ADD COLUMN input_hash VARCHAR(64)"),
    ("framework_system_task_queues", "output_hash",
     "ALTER TABLE framework_system_task_queues ADD COLUMN output_hash VARCHAR(64)"),
    ("framework_system_task_queues", "cancel_requested",
     "ALTER TABLE framework_system_task_queues ADD COLUMN cancel_requested BOOLEAN NOT NULL DEFAULT false"),
    ("framework_system_task_queues", "cancelled_at",
     "ALTER TABLE framework_system_task_queues ADD COLUMN cancelled_at TIMESTAMPTZ"),
    # framework_event_log —— 事件溯源字段（此表纯 raw DDL，无模型）
    ("framework_event_log", "event_version",
     "ALTER TABLE framework_event_log ADD COLUMN event_version INTEGER NOT NULL DEFAULT 1"),
    ("framework_event_log", "aggregate_type",
     "ALTER TABLE framework_event_log ADD COLUMN aggregate_type VARCHAR(64)"),
    ("framework_event_log", "aggregate_id",
     "ALTER TABLE framework_event_log ADD COLUMN aggregate_id VARCHAR(64)"),
    ("framework_event_log", "correlation_id",
     "ALTER TABLE framework_event_log ADD COLUMN correlation_id VARCHAR(64)"),
    ("framework_event_log", "causation_id",
     "ALTER TABLE framework_event_log ADD COLUMN causation_id VARCHAR(64)"),
    ("framework_event_log", "available_at",
     "ALTER TABLE framework_event_log ADD COLUMN available_at TIMESTAMPTZ"),
    # framework_artifact_versions —— projection lineage
    ("framework_artifact_versions", "source_content_version_id",
     "ALTER TABLE framework_artifact_versions ADD COLUMN source_content_version_id BIGINT"),
    ("framework_artifact_versions", "projection_kind",
     "ALTER TABLE framework_artifact_versions ADD COLUMN projection_kind VARCHAR(32)"),
    ("framework_artifact_versions", "target_format",
     "ALTER TABLE framework_artifact_versions ADD COLUMN target_format VARCHAR(32)"),
    ("framework_artifact_versions", "adapter_version",
     "ALTER TABLE framework_artifact_versions ADD COLUMN adapter_version VARCHAR(32)"),
    ("framework_artifact_versions", "options_sha256",
     "ALTER TABLE framework_artifact_versions ADD COLUMN options_sha256 VARCHAR(64)"),
    ("framework_artifact_versions", "fidelity_level",
     "ALTER TABLE framework_artifact_versions ADD COLUMN fidelity_level VARCHAR(16)"),
)

# 非唯一索引（扩张期安全；唯一索引留 finalize）
_INDEX_ADDS: tuple[tuple[str, str], ...] = (
    ("idx_cp_source_revision",
     "CREATE INDEX idx_cp_source_revision ON framework_content_packages(source_revision_id)"),
    ("idx_cpv_parent",
     "CREATE INDEX idx_cpv_parent ON framework_content_package_versions(parent_version_id)"),
    ("idx_cpv_retention",
     "CREATE INDEX idx_cpv_retention ON framework_content_package_versions(retention_state)"),
    ("idx_fr_file",
     "CREATE INDEX idx_fr_file ON framework_file_revisions(file_id)"),
    ("idx_ir_file",
     "CREATE INDEX idx_ir_file ON framework_ingestion_runs(file_id)"),
    ("idx_ir_status",
     "CREATE INDEX idx_ir_status ON framework_ingestion_runs(status)"),
    ("idx_ir_package",
     "CREATE INDEX idx_ir_package ON framework_ingestion_runs(package_id)"),
    ("idx_ed_status_retry",
     "CREATE INDEX idx_ed_status_retry ON framework_event_deliveries(status, retry_at)"),
    ("idx_lease_package",
     "CREATE INDEX idx_lease_package ON framework_content_edit_leases(package_id)"),
    ("idx_ra_resource",
     "CREATE INDEX idx_ra_resource ON framework_resource_analyses(resource_id)"),
    ("idx_mi_batch",
     "CREATE INDEX idx_mi_batch ON framework_migration_items(batch_id)"),
    ("idx_stq_idem",
     "CREATE INDEX idx_stq_idem ON framework_system_task_queues(idempotency_key)"),
    ("idx_stq_ingestion",
     "CREATE INDEX idx_stq_ingestion ON framework_system_task_queues(ingestion_id)"),
    ("idx_el_correlation",
     "CREATE INDEX idx_el_correlation ON framework_event_log(correlation_id)"),
    ("idx_av_source_cv",
     "CREATE INDEX idx_av_source_cv ON framework_artifact_versions(source_content_version_id)"),
)


async def _column_exists(db, table: str, column: str) -> bool:
    from sqlalchemy import text
    return bool(await db.scalar(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c)"
        ),
        {"t": table, "c": column},
    ))


async def _index_exists(db, index_name: str) -> bool:
    from sqlalchemy import text
    return bool(await db.scalar(
        text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = :n)"),
        {"n": index_name},
    ))


def _create_new_tables_sync(sync_conn) -> None:
    """用模型定义 checkfirst 建 8 张新表（复用 SQLAlchemy DDL，不手抄）。"""
    # 触发模型注册到 Base.metadata
    from app.models import content_runtime as _cr  # noqa: F401
    from app.models import product_runtime as _pr  # noqa: F401
    from app.models.base import Base

    tables = [Base.metadata.tables[name] for name in _NEW_TABLE_NAMES if name in Base.metadata.tables]
    Base.metadata.create_all(bind=sync_conn, tables=tables, checkfirst=True)


async def ensure_content_runtime_schema() -> dict:
    """扩张期幂等 DDL：建新表 + 加可空字段 + 建非唯一索引。

    - 用独立 advisory xact lock 防并发。
    - 全程 IF-NOT-EXISTS 语义，可重复运行。
    - 不做任何唯一/NOT NULL 约束切换（留 finalize 期）。
    返回本次实际变更摘要，供启动日志与 Alembic 记录。
    """
    from sqlalchemy import text

    from app.database import AsyncSessionLocal, engine

    summary = {"tables_created": [], "columns_added": [], "indexes_created": [], "skipped": False}

    # 1) 建新表（用同步连接跑 metadata.create_all，checkfirst 幂等）
    async with engine.begin() as conn:
        await conn.run_sync(_create_new_tables_sync)
    summary["tables_created"] = [n for n in _NEW_TABLE_NAMES]

    # 2) 加字段 + 索引（advisory lock + 短超时，避免热 DDL 锁风暴）
    async with AsyncSessionLocal() as db:
        locked = await db.scalar(
            text("SELECT pg_try_advisory_xact_lock(:k)"),
            {"k": CONTENT_RUNTIME_MIGRATION_LOCK_KEY},
        )
        if not locked:
            logger.info("内容运行时扩张迁移跳过：另一进程持有迁移锁")
            summary["skipped"] = True
            return summary

        await db.execute(text("SET LOCAL lock_timeout = '2000ms'"))
        await db.execute(text("SET LOCAL statement_timeout = '30000ms'"))

        for table, column, ddl in _COLUMN_ADDS:
            if await _column_exists(db, table, column):
                continue
            await db.execute(text(ddl))
            summary["columns_added"].append(f"{table}.{column}")

        for index_name, ddl in _INDEX_ADDS:
            if await _index_exists(db, index_name):
                continue
            await db.execute(text(ddl))
            summary["indexes_created"].append(index_name)

        await db.commit()

    logger.info(
        "内容运行时扩张迁移完成：新表%d 加字段%d 建索引%d",
        len(summary["tables_created"]),
        len(summary["columns_added"]),
        len(summary["indexes_created"]),
    )
    return summary
