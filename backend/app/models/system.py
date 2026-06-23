import logging
from sqlalchemy import String, Integer, Text, JSON, DateTime, ForeignKey, BigInteger, Float, Date, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone, date
from app.models.base import Base, TimestampMixin

logger = logging.getLogger("v2.models.system")


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
    # Scheduling fields for timed/recurring tasks (2025-06-21)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="当这个时间到了才该跑（可空=即时任务）")
    recur: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="周期表达: daily/hourly/weekly 或 cron")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="预计算的下次运行时间")


async def ensure_framework_scheduling_columns() -> None:
    """No-op: scheduling columns are now defined directly in the model and
    created by Base.metadata.create_all at startup.
    """
    pass

