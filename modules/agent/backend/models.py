"""Agent 模块自己的表。表名 agent_ 前缀，不加外键到框架表。"""

from __future__ import annotations

from datetime import date, datetime

from app.models.base import Base, TimestampMixin
from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class AgentUsageDaily(Base, TimestampMixin):
    """Daily aggregated model usage costs."""
    __tablename__ = "agent_usage_daily"
    __table_args__ = {"extend_existing": True}
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
    __table_args__ = {"extend_existing": True}
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
    workflow_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    workflow_step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tool_call_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_scope: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resume_target: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentConfig(Base, TimestampMixin):
    """Per-agent configuration."""
    __tablename__ = "agent_configs"
    __table_args__ = {"extend_existing": True}
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
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_response_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AgentFailureDiagnostic(Base, TimestampMixin):
    __tablename__ = "agent_failure_diagnostics"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    error_type: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentConversation(Base, TimestampMixin):
    __tablename__ = "agent_conversations"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="新对话")
    status: Mapped[str] = mapped_column(String(16), default="active")
    processing: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否有正在执行的后台任务")
    context_vars: Mapped[dict] = mapped_column(JSON, default=dict, comment="工具产出提炼的上下文变量，注入后续提示词")


class AgentMessage(Base, TimestampMixin):
    __tablename__ = "agent_messages"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16))  # user/assistant
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active", comment="active | archived")
    edited_from_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="B'来源旧B的ID")
    branch_root_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="编辑分叉点消息ID")


class AgentMessageMeta(Base, TimestampMixin):
    __tablename__ = "agent_message_meta"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    thinking: Mapped[str] = mapped_column(Text, default="")
    references: Mapped[list] = mapped_column(JSON, default=list)
    tool_events: Mapped[list] = mapped_column(JSON, default=list)
    timeline: Mapped[list] = mapped_column(JSON, default=list)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# ── 三层提示词系统 ──────────────────────────────────────────

class AgentSystemPrompt(Base, TimestampMixin):
    """全局 1 份：Agent 执行边界 / 人格 / 规则，管理员维护。"""
    __tablename__ = "agent_system_prompt"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentEnterprisePrompt(Base, TimestampMixin):
    """全局 1 份：公司知识 / 规则 / 话术，管理员维护。"""
    __tablename__ = "agent_enterprise_prompt"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentUserProfile(Base, TimestampMixin):
    """每用户 1 份：系统自动进化的个人画像（语气、禁忌、关注点、习惯）。"""
    __tablename__ = "agent_user_profile"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    profile_data: Mapped[str] = mapped_column(Text, default="")  # JSON: tone/taboo/focus/habits
    version: Mapped[int] = mapped_column(Integer, default=0)
    evolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    conversation_count: Mapped[int] = mapped_column(Integer, default=0)


class ContextSnapshot(Base, TimestampMixin):
    __tablename__ = "agent_context_snapshots"
    __table_args__ = {"extend_existing": True}
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


# ── Skill Governance Models ──────────────────────────────────────


class SkillRegistryItem(Base, TimestampMixin):
    """Skill registry: DB-side skill definition with governance metadata."""
    __tablename__ = "agent_skill_registry"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="manual")
    source_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_tools: Mapped[list] = mapped_column(JSON, default=list)
    paths: Mapped[list] = mapped_column(JSON, default=list)
    scope: Mapped[str] = mapped_column(String(32), default="global")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_status: Mapped[str] = mapped_column(String(32), default="pending_approval")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class SkillApproval(Base, TimestampMixin):
    """Approval requests for skill changes."""
    __tablename__ = "agent_skill_approvals"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requested_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_approval")
    requested_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_result_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SkillProvenance(Base, TimestampMixin):
    """Provenance trail for every skill change."""
    __tablename__ = "agent_skill_provenance"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SkillUsage(Base, TimestampMixin):
    """Per-invocation usage tracking for skills."""
    __tablename__ = "agent_skill_usage"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Review / Fork Models ─────────────────────────────────────────


class ReviewTask(Base, TimestampMixin):
    """Background review fork task tracking."""
    __tablename__ = "agent_review_tasks"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    review_context: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewResult(Base, TimestampMixin):
    """A single structured proposal from a review fork."""
    __tablename__ = "agent_review_results"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    review_task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    result_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="proposal")
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ── Checkpoint / Trajectory Models ──────────────────────────────


class AgentCheckpoint(Base, TimestampMixin):
    """Agent execution checkpoint for recovery and replay."""
    __tablename__ = "agent_checkpoints"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    checkpoint_id: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    step: Mapped[int] = mapped_column(Integer, default=0)
    channel_values: Mapped[dict] = mapped_column(JSON, default=dict)
    extra_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    workflow_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    workflow_step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    checkpoint_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resume_cursor: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AgentTrajectoryRecord(Base, TimestampMixin):
    """Lightweight trajectory trace for research and analysis."""
    __tablename__ = "agent_trajectory_records"
    __table_args__ = (
        # Unique constraint enforced via uq_trajectory_conv_turn unique INDEX
        # (created in init_db.ensure_trajectory_unique_constraint).
        # UniqueConstraint is NOT used because PG17 does not support
        # ADD CONSTRAINT IF NOT EXISTS, but CREATE UNIQUE INDEX IF NOT EXISTS works.
        {"extend_existing": True},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    turn_index: Mapped[int] = mapped_column(Integer, default=0)
    user_input: Mapped[str] = mapped_column(Text, default="")
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)
    tool_results: Mapped[list] = mapped_column(JSON, default=list)
    assistant_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_recovery: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    thinking_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    profile_signals: Mapped[list] = mapped_column(JSON, default=list)
    error_occurred: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentWorkflowRecipe(Base, TimestampMixin):
    """Per-user mined workflow recipe for shortest-path reuse.

    Generated asynchronously by a background job that analyzes successful
    turn trajectories. Each recipe describes the shortest known tool chain
    for a given user intent, along with scoring and provenance fields.
    """
    __tablename__ = "agent_workflow_recipes"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    intent_label: Mapped[str] = mapped_column(String(128), default="")
    trigger_condition: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list] = mapped_column(JSON, default=list)
    tools_used: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="proposal")
    version: Mapped[int] = mapped_column(Integer, default=1)
    success_weight: Mapped[float] = mapped_column(Float, default=0.0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_tool_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_trajectory_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_experience_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


# ── Profile 2.0 Models ──────────────────────────────────────────


class AgentRoleProfile(Base, TimestampMixin):
    """Role/position profile: defines behavioral expectations per role."""
    __tablename__ = "agent_role_profiles"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str | None] = mapped_column(Text, nullable=True)
    taboos: Mapped[list] = mapped_column(JSON, default=list)
    focus_areas: Mapped[list] = mapped_column(JSON, default=list)
    habits: Mapped[list] = mapped_column(JSON, default=list)
    allowed_tools: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentEnterpriseProfile(Base, TimestampMixin):
    """Enterprise-level profile: company-wide behavioral context."""
    __tablename__ = "agent_enterprise_profiles"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    enterprise_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, default="default")
    enterprise_name: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str | None] = mapped_column(Text, nullable=True)
    taboos: Mapped[list] = mapped_column(JSON, default=list)
    focus_areas: Mapped[list] = mapped_column(JSON, default=list)
    business_rules: Mapped[list] = mapped_column(JSON, default=list)
    communication_style: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentMarketProfile(Base, TimestampMixin):
    """Market/Product/Brand/Competitor profile."""
    __tablename__ = "agent_market_profiles"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_type: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentProfileSignal(Base, TimestampMixin):
    """Profile signal pool: low-confidence observations that may
    eventually evolve into profile changes."""
    __tablename__ = "agent_profile_signals"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_profile_type: Mapped[str] = mapped_column(String(32), default="user")
    signal_data: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(32), default="auto")
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Tool Guidance Models ────────────────────────────────────────────


class AgentToolGuide(Base, TimestampMixin):
    """Tool guidance control plane: per-owner per-agent per-tool guidance.

    Each record defines how an agent should use a specific tool,
    including usage guidance, failure policy, and acceptance policy.
    Supports versioning, disable, rollback, and candidate promotion.
    """
    __tablename__ = "agent_tool_guides"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    agent_code: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="global")
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(256), default="")
    guide_text: Mapped[str] = mapped_column(Text, default="")
    failure_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    acceptance_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    source: Mapped[str] = mapped_column(String(32), default="manual")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentToolGuideVersion(Base, TimestampMixin):
    """Version history for tool guides."""
    __tablename__ = "agent_tool_guide_versions"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guide_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_code: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="")
    guide_text: Mapped[str] = mapped_column(Text, default="")
    failure_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    acceptance_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active")
    source: Mapped[str] = mapped_column(String(32), default="manual")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AgentToolGuideCandidate(Base, TimestampMixin):
    """Candidate queue for tool guide proposals awaiting review/promotion."""
    __tablename__ = "agent_tool_guide_candidates"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_code: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="agent")
    title: Mapped[str] = mapped_column(String(256), default="")
    guide_text: Mapped[str] = mapped_column(Text, default="")
    failure_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    acceptance_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    source: Mapped[str] = mapped_column(String(32), default="mined")
    source_trajectory_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    proposed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_guide_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)



class AgentContextCompaction(Base, TimestampMixin):
    """Persisted context compaction for async, off-critical-path compression.

    Each record represents one compaction run; only ``status='ready'`` is
    visible to the request path.  The unique index on
    ``(conversation_id, until_event_id, generation)`` (created in init_db)
    ensures idempotency across multi-worker retries.
    """
    __tablename__ = "agent_context_compactions"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    until_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="building")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    folded_event_ids: Mapped[list] = mapped_column(JSON, default=list)
    token_before: Mapped[int] = mapped_column(Integer, default=0)
    token_after: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


from .models_prompt import AgentPrompt as AgentPrompt
