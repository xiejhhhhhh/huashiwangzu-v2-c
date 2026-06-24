"""Agent 模块自己的表。表名 agent_ 前缀，不加外键到框架表。"""
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Integer, JSON, String, Text, BigInteger, DateTime, Date, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class AgentUsageDaily(Base, TimestampMixin):
    """Daily aggregated model usage costs."""
    __tablename__ = "agent_usage_daily"
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
    """Sensitive operation approval queue."""
    __tablename__ = "agent_approval_queue"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_code: Mapped[str] = mapped_column(String(64), default="")
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_args: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    requested_by: Mapped[int] = mapped_column(Integer, nullable=False)
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentConfig(Base, TimestampMixin):
    """Per-agent configuration."""
    __tablename__ = "agent_configs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(128), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(String(256), default="")
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
    response_format: Mapped[str] = mapped_column(String(16), default="text")
    log_prompt_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    log_response_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sensitive_action_policy: Mapped[str] = mapped_column(String(16), default="confirm")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentEvent(Base, TimestampMixin):
    __tablename__ = "agent_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_response_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AgentConversation(Base, TimestampMixin):
    __tablename__ = "agent_conversations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="新对话")
    status: Mapped[str] = mapped_column(String(16), default="active")
    processing: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否有正在执行的后台任务")


class AgentMessage(Base, TimestampMixin):
    __tablename__ = "agent_messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16))  # user/assistant
    content: Mapped[str] = mapped_column(Text, default="")


class AgentMessageMeta(Base, TimestampMixin):
    __tablename__ = "agent_message_meta"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    thinking: Mapped[str] = mapped_column(Text, default="")
    references: Mapped[list] = mapped_column(JSON, default=list)
    tool_events: Mapped[list] = mapped_column(JSON, default=list)
    timeline: Mapped[list] = mapped_column(JSON, default=list)


# ── 三层提示词系统 ──────────────────────────────────────────

class AgentSystemPrompt(Base, TimestampMixin):
    """全局 1 份：Agent 执行边界 / 人格 / 规则，管理员维护。"""
    __tablename__ = "agent_system_prompt"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentEnterprisePrompt(Base, TimestampMixin):
    """全局 1 份：公司知识 / 规则 / 话术，管理员维护。"""
    __tablename__ = "agent_enterprise_prompt"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentUserProfile(Base, TimestampMixin):
    """每用户 1 份：系统自动进化的个人画像（语气、禁忌、关注点、习惯）。"""
    __tablename__ = "agent_user_profile"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    profile_data: Mapped[str] = mapped_column(Text, default="")  # JSON: tone/taboo/focus/habits
    version: Mapped[int] = mapped_column(Integer, default=0)
    evolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    conversation_count: Mapped[int] = mapped_column(Integer, default=0)


class ContextSnapshot(Base, TimestampMixin):
    __tablename__ = "agent_context_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="pre_compress / post_compress / periodic")
    event_id_before: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="压缩前最后事件id")
    event_id_after: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="压缩后最后事件id")
    message_count_before: Mapped[int] = mapped_column(Integer, default=0)
    message_count_after: Mapped[int] = mapped_column(Integer, default=0)
    token_estimate_before: Mapped[int] = mapped_column(Integer, default=0)
    token_estimate_after: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="压缩/快照摘要")
    snapshot_data: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="完整消息快照（用于回放）")
    compression_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    restored_from: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="从哪个snapshot恢复")


# ── Agent 状态数据表（原文件存储迁移至 PostgreSQL） ──────────────

class AgentHookRun(Base, TimestampMixin):
    """Hook run history for lifecycle governance."""
    __tablename__ = "agent_hook_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    hook_name: Mapped[str] = mapped_column(String(128), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentRecallQuality(Base, TimestampMixin):
    """Recall quality metrics for governance dashboard."""
    __tablename__ = "agent_recall_qualities"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    layer: Mapped[str] = mapped_column(String(32), nullable=False)
    limit_val: Mapped[int] = mapped_column(Integer, nullable=False)
    total_results: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    result_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)


class AgentBudgetState(Base, TimestampMixin):
    """Per-conversation budget tracker state."""
    __tablename__ = "agent_budget_states"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    rounds_data: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentStuckRound(Base, TimestampMixin):
    """Per-conversation stuck detector round history."""
    __tablename__ = "agent_stuck_rounds"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    rounds_data: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentFailureDiagnostic(Base, TimestampMixin):
    """Structured failure diagnostic records."""
    __tablename__ = "agent_failure_diagnostics"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    error_type: Mapped[str] = mapped_column(String(64), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


from .models_prompt import AgentPrompt
