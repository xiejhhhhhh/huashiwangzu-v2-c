"""Agent 模块自己的表。表名 agent_ 前缀，不加外键到框架表。"""
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Integer, JSON, String, Text, BigInteger, DateTime, Date, Float, UniqueConstraint
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


class AgentMaintenanceState(Base, TimestampMixin):
    """Single-row table for cross-worker hook lifecycle state.

    Enforced by CHECK (id = 1) — only one row ever exists.
    Each worker upserts its heartbeat; the admin endpoint reads the
    latest state for observability across all workers.
    """
    __tablename__ = "agent_maintenance_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    maintenance_status: Mapped[str] = mapped_column(String(16), default="stopped")
    worker_id: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)


from .models_prompt import AgentPrompt


# ── Memory Snapshot / Frozen Snapshot Models ────────────────────────────


class MemorySnapshot(Base, TimestampMixin):
    """Persistent frozen memory snapshot for long-running conversations.

    Unlike ``ContextSnapshot`` (which records pre/post-compress state for
    diagnostics), this table holds the *memory content* of a snapshot —
    the actual stable rules, chunks, and semantic memories that were selected
    at a given turn.  Long tasks can request ``frozen_key`` at turn N and
    reuse the same memory context through turn N+M without re-recall.

    Snapshots are created by ``freeze_memory_snapshot()`` (which writes to
    a process cache) and can be optionally persisted here for cross-worker
    reuse.
    """
    __tablename__ = "agent_memory_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(64), default="")
    snapshot_type: Mapped[str] = mapped_column(String(32), default="conversation_start")
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    # Serialised memory content
    stable_rules_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    chunks_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    semantic_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    selection_audit: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# ── Review / Skill Governance Models ────────────────────────────────────


class ReviewTask(Base, TimestampMixin):
    """A background review task spawned after a conversation turn.
    
    Runs with restricted tools (memory/skill only) and produces structured
    proposals.  Does not interact with the user.
    """
    __tablename__ = "agent_review_tasks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    review_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewResult(Base, TimestampMixin):
    """A structured proposal produced by a background review task.
    
    Types:
      - stable_rule: proposal to persist a chat-learned rule
      - chunk_proposal: proposal to create/update a memory chunk
      - experience_proposal: proposal to save a reusable experience
      - skill_create: proposal to create a new skill
      - skill_patch: proposal to modify an existing skill
      - profile_note: suggested user profile update
      - safety_note: safety observation
    """
    __tablename__ = "agent_review_results"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    review_task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    result_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="proposal")
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SkillRegistryItem(Base, TimestampMixin):
    """DB-backed skill record for lifecycle governance (beyond file-scan).
    
    A skill can originate from a file scan or be authored via skill_manage.
    When both file and DB records exist for the same name, the DB record
    takes precedence for status/approval.
    """
    __tablename__ = "agent_skill_registry"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="file_scan")
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    allowed_tools: Mapped[list | None] = mapped_column(JSON, nullable=True)
    paths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    scope: Mapped[str] = mapped_column(String(32), default="global")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_status: Mapped[str] = mapped_column(String(16), default="pending_approval")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SkillApproval(Base, TimestampMixin):
    """Approval record for skill create/update/delete operations."""
    __tablename__ = "agent_skill_approvals"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requested_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending_approval")
    requested_by: Mapped[int] = mapped_column(Integer, nullable=False)
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_result_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class SkillProvenance(Base, TimestampMixin):
    """Provenance trail for skill origins and modifications."""
    __tablename__ = "agent_skill_provenance"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SkillUsage(Base, TimestampMixin):
    """Per-invocation usage tracking for skills."""
    __tablename__ = "agent_skill_usage"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Understanding Loop Models ───────────────────────────────────────────


class UnderstandingPacket(Base, TimestampMixin):
    """Structured understanding packet produced by the understanding loop.

    Created when a high-ambiguity or high-cost task triggers the
    understanding orchestrator. Contains the consolidated output from
    multiple understanding roles (intent_clarifier, concern_miner,
    plan_critic, retrieval_evidence).

    Owner_id is required and must be set from the runtime caller.
    """
    __tablename__ = "agent_understanding_packets"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    trigger_reason: Mapped[str] = mapped_column(String(64), default="high_ambiguity")
    user_input: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(Text, default="")
    concerns: Mapped[list] = mapped_column(JSON, default=list)
    plan_critique: Mapped[str] = mapped_column(Text, default="")
    retrieval_evidence: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    rounds_used: Mapped[int] = mapped_column(Integer, default=0)
    roles_executed: Mapped[list] = mapped_column(JSON, default=list)
    resolved_profile_key: Mapped[str] = mapped_column(String(64), default="")
    resolved_template: Mapped[str] = mapped_column(String(64), default="default")


# ── Checkpoint for crash recovery ────────────────────────────────────────

class AgentCheckpoint(Base, TimestampMixin):
    """Per-round execution checkpoint for crash recovery.

    Saved after each tool round when ``enable_checkpointer`` is True.
    Enables resuming a conversation from the last checkpoint after a
    worker crash instead of losing the entire turn.

    Columns deliberately avoid the name ``metadata`` (SQLAlchemy reserved
    word).  ``owner_id`` is a dedicated NOT NULL column (never buried in
    JSON).
    """
    __tablename__ = "agent_checkpoints"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    checkpoint_id: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    step: Mapped[int] = mapped_column(Integer, default=0)
    channel_values: Mapped[dict] = mapped_column(JSON, default=dict, comment="messages/tool_events/timeline/pending_events")
    extra_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="extra metadata, NOT the SQLAlchemy-reserved 'metadata'")
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("conversation_id", "checkpoint_id", name="uq_agent_checkpoint_pair"),
    )


class UnderstandingEvent(Base, TimestampMixin):
    """Per-role call record within an understanding loop.

    Each role (intent_clarifier, concern_miner, etc.) produces one event.
    Enables audit of what each role contributed.
    """
    __tablename__ = "agent_understanding_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    packet_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, default="")
    response: Mapped[str] = mapped_column(Text, default="")
    profile_key: Mapped[str] = mapped_column(String(64), default="")
    round_index: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
