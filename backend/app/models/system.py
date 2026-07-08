import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

logger = logging.getLogger("v2.models.system")
TASK_QUEUE_MIGRATION_LOCK_KEY = 94022027


class SystemLog(Base, TimestampMixin):
    __tablename__ = "framework_system_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), default="info")
    module: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(128), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    request_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class Notification(Base, TimestampMixin):
    __tablename__ = "framework_system_notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    notification_type: Mapped[str] = mapped_column(String(32), default="system")
    status: Mapped[str] = mapped_column(String(16), default="published")
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserNotificationRead(Base, TimestampMixin):
    __tablename__ = "framework_system_notification_reads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(Integer, ForeignKey("framework_system_notifications.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Feedback(Base, TimestampMixin):
    __tablename__ = "framework_system_feedbacks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(32), default="bug")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_url: Mapped[str] = mapped_column(Text, default="")
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    handler_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Task(Base, TimestampMixin):
    """Personal task (assignable to users)"""
    __tablename__ = "framework_system_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    assignee_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=True)
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    priority: Mapped[str] = mapped_column(String(8), default="medium")


class Setting(Base, TimestampMixin):
    """System configuration key-value store"""
    __tablename__ = "framework_system_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(String(255), default="")


class SystemTaskQueue(Base, TimestampMixin):
    """Background task queue for async job management"""
    __tablename__ = "framework_system_task_queues"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    module: Mapped[str] = mapped_column(String(64), default="")
    creator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("framework_user_accounts.id"), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    stage_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lane_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ready_status: Mapped[str] = mapped_column(String(32), default="ready")
    dependency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Scheduling fields for timed/recurring tasks (2025-06-21)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="当这个时间到了才该跑（可空=即时任务）")
    recur: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="周期表达: daily/hourly/weekly 或 cron")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="预计算的下次运行时间")


@dataclass(frozen=True)
class _TaskQueueColumnMigration:
    column: str
    ddl: str


async def _task_queue_column_exists(db, column: str) -> bool:
    from sqlalchemy import text

    return bool(
        await db.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'framework_system_task_queues'
                      AND column_name = :column
                )
                """
            ),
            {"column": column},
        )
    )


async def _task_queue_index_exists(db, index_name: str) -> bool:
    from sqlalchemy import text

    return bool(await db.scalar(text("SELECT to_regclass(:index_name) IS NOT NULL"), {"index_name": index_name}))


async def ensure_framework_scheduling_columns() -> None:
    """Ensure task queue scheduling and DAG dispatch columns exist without hot DDL locks."""
    from sqlalchemy import text

    from app.database import AsyncSessionLocal

    columns = [
        _TaskQueueColumnMigration("scheduled_at", "ALTER TABLE framework_system_task_queues ADD COLUMN scheduled_at TIMESTAMPTZ"),
        _TaskQueueColumnMigration("recur", "ALTER TABLE framework_system_task_queues ADD COLUMN recur VARCHAR(32)"),
        _TaskQueueColumnMigration("next_run_at", "ALTER TABLE framework_system_task_queues ADD COLUMN next_run_at TIMESTAMPTZ"),
        _TaskQueueColumnMigration("document_id", "ALTER TABLE framework_system_task_queues ADD COLUMN document_id BIGINT"),
        _TaskQueueColumnMigration("stage_key", "ALTER TABLE framework_system_task_queues ADD COLUMN stage_key VARCHAR(64)"),
        _TaskQueueColumnMigration("lane_key", "ALTER TABLE framework_system_task_queues ADD COLUMN lane_key VARCHAR(64)"),
        _TaskQueueColumnMigration("ready_status", "ALTER TABLE framework_system_task_queues ADD COLUMN ready_status VARCHAR(32) DEFAULT 'ready'"),
        _TaskQueueColumnMigration("dependency_key", "ALTER TABLE framework_system_task_queues ADD COLUMN dependency_key VARCHAR(128)"),
        _TaskQueueColumnMigration("blocked_reason", "ALTER TABLE framework_system_task_queues ADD COLUMN blocked_reason TEXT"),
    ]
    indexes = [
        (
            "idx_framework_task_queue_dispatch",
            "CREATE INDEX idx_framework_task_queue_dispatch ON framework_system_task_queues(status, ready_status, lane_key, priority DESC, id)",
        ),
        (
            "idx_framework_task_queue_stage",
            "CREATE INDEX idx_framework_task_queue_stage ON framework_system_task_queues(task_type, stage_key, status)",
        ),
        (
            "idx_framework_task_queue_doc_stage",
            "CREATE INDEX idx_framework_task_queue_doc_stage ON framework_system_task_queues(task_type, document_id, stage_key, status)",
        ),
    ]
    try:
        async with AsyncSessionLocal() as db:
            locked = await db.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": TASK_QUEUE_MIGRATION_LOCK_KEY},
            )
            if not locked:
                logger.info("Task queue DAG migration skipped: another process owns migration lock")
                return

            await db.execute(text("SET LOCAL lock_timeout = '1000ms'"))
            await db.execute(text("SET LOCAL statement_timeout = '10000ms'"))

            changed = False
            existing_columns = {
                migration.column: await _task_queue_column_exists(db, migration.column)
                for migration in columns
            }
            for migration in columns:
                if existing_columns[migration.column]:
                    continue
                await db.execute(text(migration.ddl))
                changed = True

            if existing_columns.get("ready_status", True):
                missing_ready_status = await db.scalar(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM framework_system_task_queues
                            WHERE ready_status IS NULL
                            LIMIT 1
                        )
                        """
                    )
                )
                if missing_ready_status:
                    await db.execute(text("UPDATE framework_system_task_queues SET ready_status = 'ready' WHERE ready_status IS NULL"))
            if existing_columns.get("document_id", True) and existing_columns.get("stage_key", True):
                missing_doc_stage = await db.scalar(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM framework_system_task_queues
                            WHERE task_type = 'kb_pipeline_stage'
                              AND parameters IS NOT NULL
                              AND parameters ~ '^\\s*\\{'
                              AND (document_id IS NULL OR stage_key IS NULL)
                            LIMIT 1
                        )
                        """
                    )
                )
                if missing_doc_stage:
                    await db.execute(
                        text(
                            """
                            UPDATE framework_system_task_queues
                            SET
                                document_id = COALESCE(document_id, NULLIF(parameters::jsonb->>'document_id', '')::bigint),
                                stage_key = COALESCE(stage_key, parameters::jsonb->>'stage')
                            WHERE task_type = 'kb_pipeline_stage'
                              AND parameters IS NOT NULL
                              AND parameters ~ '^\\s*\\{'
                              AND (document_id IS NULL OR stage_key IS NULL)
                            """
                        )
                    )
            if existing_columns.get("lane_key", True) and existing_columns.get("stage_key", True):
                missing_lane = await db.scalar(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM framework_system_task_queues
                            WHERE task_type = 'kb_pipeline_stage'
                              AND lane_key IS NULL
                              AND stage_key IS NOT NULL
                            LIMIT 1
                        )
                        """
                    )
                )
                if missing_lane:
                    await db.execute(
                        text(
                            """
                            UPDATE framework_system_task_queues
                            SET lane_key = CASE stage_key
                                WHEN 'source_validate' THEN 'local_preprocess'
                                WHEN 'parse_index' THEN 'local_preprocess'
                                WHEN 'raw_text' THEN 'local_preprocess'
                                WHEN 'raw_ocr' THEN 'model_analysis'
                                WHEN 'raw_vision' THEN 'model_analysis'
                                WHEN 'fusion' THEN 'model_analysis'
                                WHEN 'profile' THEN 'model_analysis'
                                WHEN 'graph' THEN 'model_analysis'
                                WHEN 'relations' THEN 'relation_build'
                                ELSE lane_key
                            END
                            WHERE task_type = 'kb_pipeline_stage'
                              AND lane_key IS NULL
                              AND stage_key IS NOT NULL
                            """
                        )
                    )

            for index_name, index_ddl in indexes:
                if not await _task_queue_index_exists(db, index_name):
                    await db.execute(text(index_ddl))
                    changed = True
            await db.commit()
            if changed:
                logger.info("Task queue DAG migration applied missing columns/indexes")
    except Exception as exc:
        logger.warning("Task queue DAG migration skipped to avoid startup lock contention: %s", exc)
