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


class AgentUsageDaily(Base, TimestampMixin):
    """Daily aggregated model usage costs. Framework-level tracking."""
    __tablename__ = "framework_agent_usage_daily"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    model_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="")
    module: Mapped[str] = mapped_column(String(64), default="")
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)


class ApprovalQueue(Base, TimestampMixin):
    """Sensitive operation approval queue.

    When an agent tool is flagged as sensitive and the agent's policy is
    'confirm', a row is inserted here. The admin either approves or rejects
    it. Status transitions: pending → approved | rejected.
    """
    __tablename__ = "framework_approval_queue"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_code: Mapped[str] = mapped_column(String(64), default="", comment="Which agent requested")
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Sensitive tool name")
    tool_args: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON tool arguments")
    status: Mapped[str] = mapped_column(String(16), default="pending", comment="pending|approved|rejected")
    requested_by: Mapped[int] = mapped_column(Integer, nullable=False, comment="User who triggered the action")
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Admin who decided")
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Admin rejection reason or note")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentConfig(Base, TimestampMixin):
    """Per-agent configuration. References models.json profile keys.

    Each row represents one independent agent (erp_chat, file_router, etc.).
    The 'sensitive_action_policy' column stores the default sensitive operation
    strategy for this agent: 'allow' | 'confirm' | 'block'.
    """
    __tablename__ = "framework_agent_configs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="Unique agent identifier")
    agent_name: Mapped[str] = mapped_column(String(128), default="", comment="Display name")
    provider: Mapped[str] = mapped_column(String(64), default="", comment="Provider name from models.json")
    model: Mapped[str] = mapped_column(String(64), default="", comment="Model profile key from models.json")
    system_prompt: Mapped[str] = mapped_column(Text, default="", comment="System prompt for this agent")
    purpose: Mapped[str] = mapped_column(String(256), default="", comment="Brief purpose description")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    max_concurrency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cooldown_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=3)
    daily_call_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    monthly_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_format: Mapped[str] = mapped_column(String(16), default="text", comment="text|json_object")
    log_prompt_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    log_response_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sensitive_action_policy: Mapped[str] = mapped_column(String(16), default="confirm", comment="allow|confirm|block")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


_MIGRATIONS_DONE = False


async def ensure_usage_daily_table() -> None:
    """Create framework_agent_usage_daily if not exists. Idempotent."""
    from sqlalchemy import text, exc as sa_exc
    from app.database import engine
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS framework_agent_usage_daily (
                id BIGSERIAL PRIMARY KEY,
                usage_date DATE NOT NULL,
                model_key VARCHAR(64) NOT NULL,
                provider VARCHAR(32) DEFAULT '',
                module VARCHAR(64) DEFAULT '',
                call_count INTEGER DEFAULT 0,
                prompt_tokens BIGINT DEFAULT 0,
                completion_tokens BIGINT DEFAULT 0,
                cost DOUBLE PRECISION DEFAULT 0.0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        # Ensure unique constraint (PG: CREATE UNIQUE INDEX IF NOT EXISTS)
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_usage_daily
            ON framework_agent_usage_daily (usage_date, model_key, provider, module)
        """))


async def ensure_approval_queue_table() -> None:
    """Create framework_approval_queue if not exists. Idempotent."""
    from sqlalchemy import text
    from app.database import engine
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS framework_approval_queue (
                id BIGSERIAL PRIMARY KEY,
                agent_code VARCHAR(64) DEFAULT '',
                tool_name VARCHAR(128) NOT NULL,
                tool_args TEXT,
                status VARCHAR(16) DEFAULT 'pending',
                requested_by INTEGER NOT NULL,
                decided_by INTEGER,
                conversation_id BIGINT,
                reason TEXT,
                decided_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))


async def ensure_agent_configs_table() -> None:
    """Create framework_agent_configs if not exists. Idempotent."""
    from sqlalchemy import text, exc as sa_exc
    from app.database import engine

    ddl = """
        CREATE TABLE IF NOT EXISTS framework_agent_configs (
            id BIGSERIAL PRIMARY KEY,
            agent_code VARCHAR(64) NOT NULL UNIQUE,
            agent_name VARCHAR(128) DEFAULT '',
            provider VARCHAR(64) DEFAULT '',
            model VARCHAR(64) DEFAULT '',
            system_prompt TEXT DEFAULT '',
            purpose VARCHAR(256) DEFAULT '',
            enabled BOOLEAN DEFAULT TRUE,
            temperature DOUBLE PRECISION,
            top_p DOUBLE PRECISION,
            max_tokens INTEGER,
            timeout_ms INTEGER,
            fallback_model VARCHAR(64),
            fallback_enabled BOOLEAN DEFAULT FALSE,
            max_concurrency INTEGER,
            cooldown_seconds INTEGER,
            retry_count INTEGER DEFAULT 3,
            daily_call_limit INTEGER,
            daily_budget DOUBLE PRECISION,
            monthly_budget DOUBLE PRECISION,
            response_format VARCHAR(16) DEFAULT 'text',
            log_prompt_enabled BOOLEAN DEFAULT TRUE,
            log_response_enabled BOOLEAN DEFAULT TRUE,
            sensitive_action_policy VARCHAR(16) DEFAULT 'confirm',
            updated_by INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
    async with engine.begin() as conn:
        await conn.execute(text(ddl))
    logger.info("Ensured framework_agent_configs table")


async def ensure_framework_scheduling_columns() -> None:
    """ALTER ADD COLUMN IF NOT EXISTS for SystemTaskQueue scheduling fields.
    Idempotent — safe to call multiple times.
    """
    global _MIGRATIONS_DONE
    if _MIGRATIONS_DONE:
        return
    from sqlalchemy import text
    from app.database import engine
    cols = [
        ("scheduled_at", "TIMESTAMP WITH TIME ZONE"),
        ("recur", "VARCHAR(32)"),
        ("next_run_at", "TIMESTAMP WITH TIME ZONE"),
    ]
    async with engine.begin() as conn:
        for col_name, col_type in cols:
            await conn.execute(text(
                f"ALTER TABLE framework_system_task_queues "
                f"ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
            ))
    _MIGRATIONS_DONE = True

