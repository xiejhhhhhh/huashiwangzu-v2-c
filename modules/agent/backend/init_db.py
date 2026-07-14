"""Agent 模块表初始化：确保三层提示词默认数据存在，并执行无痛迁移。"""
import logging
import os

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AgentEnterprisePrompt, AgentSystemPrompt, AgentUserProfile
from .models_prompt import AgentPrompt
from .prompt_seeds import (
    AGENT_PROMPT_SEEDS,
    ENTERPRISE_PROMPT,
    SYSTEM_BASE_PROMPT,
)

logger = logging.getLogger("v2.agent").getChild("init_db")

DEFAULT_SYSTEM_PROMPT = SYSTEM_BASE_PROMPT

DEFAULT_ENTERPRISE_PROMPT = ENTERPRISE_PROMPT

_LEGACY_SYSTEM_PROMPT_MARKERS = (
    "你是华世王镞（Huashi Wangzu）桌面 AI 助手。",
    "知识库使用规则：",
    "产品/成分/品牌/规格资料",
)


def _looks_like_legacy_system_prompt(content: str) -> bool:
    return all(marker in (content or "") for marker in _LEGACY_SYSTEM_PROMPT_MARKERS)


async def ensure_default_prompts(db: AsyncSession) -> None:
    """确保系统提示词和企业提示词各至少有一条默认记录。"""
    r = await db.execute(select(AgentSystemPrompt).limit(1))
    if not r.scalar_one_or_none():
        db.add(AgentSystemPrompt(content=DEFAULT_SYSTEM_PROMPT, version=1))
        logger.info("Created default system prompt")

    r = await db.execute(select(AgentEnterprisePrompt).limit(1))
    if not r.scalar_one_or_none():
        db.add(AgentEnterprisePrompt(content=DEFAULT_ENTERPRISE_PROMPT, version=1))
        logger.info("Created default enterprise prompt")

    await db.commit()


async def ensure_user_profile(db: AsyncSession, owner_id: int) -> AgentUserProfile:
    """确保用户有个人画像记录，没有则创建空画像。"""
    r = await db.execute(
        select(AgentUserProfile).where(AgentUserProfile.owner_id == owner_id)
    )
    profile = r.scalar_one_or_none()
    if not profile:
        profile = AgentUserProfile(
            owner_id=owner_id,
            profile_data="{}",
            version=0,
            conversation_count=0,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


async def ensure_default_agent_prompts(db: AsyncSession) -> None:
    """Seed DB-backed Agent prompts without clobbering edited content."""
    for stmt in [
        "ALTER TABLE agent_prompts ALTER COLUMN owner_id DROP NOT NULL",
        "ALTER TABLE agent_prompts ADD COLUMN IF NOT EXISTS key VARCHAR(128) DEFAULT ''",
        "ALTER TABLE agent_prompts ADD COLUMN IF NOT EXISTS scope VARCHAR(16) DEFAULT 'user'",
        "ALTER TABLE agent_prompts ADD COLUMN IF NOT EXISTS is_read_only BOOLEAN DEFAULT FALSE",
        "ALTER TABLE agent_prompts ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1",
        "CREATE INDEX IF NOT EXISTS ix_agent_prompts_key ON agent_prompts(key)",
    ]:
        try:
            await db.execute(text(stmt))
        except Exception as exc:
            logger.warning("Prompt table migration skipped for %s: %s", stmt, exc)
            await db.rollback()
    for seed in AGENT_PROMPT_SEEDS:
        result = await db.execute(select(AgentPrompt).where(AgentPrompt.key == seed.key).limit(1))
        prompt = result.scalar_one_or_none()
        if prompt:
            prompt.title = prompt.title or seed.title
            prompt.category = prompt.category or seed.category
            prompt.scope = prompt.scope or seed.scope
            prompt.is_read_only = bool(prompt.is_read_only or seed.is_read_only)
            prompt.is_active = bool(prompt.is_active if prompt.is_active is not None else seed.is_active)
            prompt.status = prompt.status or seed.status
            prompt.version = prompt.version or 1
            if seed.key == "agent.system.base" and _looks_like_legacy_system_prompt(prompt.content):
                prompt.content = SYSTEM_BASE_PROMPT
                prompt.version = (prompt.version or 1) + 1
                logger.info("Migrated legacy system prompt seed to open protocol")
            continue
        db.add(AgentPrompt(
            owner_id=None,
            key=seed.key,
            title=seed.title,
            category=seed.category,
            content=seed.content,
            scope=seed.scope,
            is_read_only=seed.is_read_only,
            is_active=seed.is_active,
            status=seed.status,
            version=1,
        ))
    await db.commit()
    logger.info("Ensured %d agent prompt seeds", len(AGENT_PROMPT_SEEDS))


async def ensure_timeline_column(db: AsyncSession) -> None:
    """无痛迁移：旧 agent_message_meta 表缺 timeline 列时自动补齐。"""
    try:
        await db.execute(text("ALTER TABLE agent_message_meta ADD COLUMN IF NOT EXISTS timeline JSON DEFAULT '[]'::json"))
        await db.commit()
        logger.info("Migration: ensured timeline column on agent_message_meta")
    except Exception as e:
        # IF NOT EXISTS handles "column already exists"; this catches real errors only
        await db.rollback()
        if hasattr(e, 'orig') and hasattr(e.orig, 'pgcode'):
            # PostgreSQL error code — log and swallow known migration-safe errors
            logger.warning("Migration: timeline column check (%s): %s", e.orig.pgcode, e)
        else:
            # Unknown error — log but don't crash the startup
            logger.warning("Migration: timeline column check failed: %s", e)


NEW_SYSTEM_PROMPT_CONTENT = SYSTEM_BASE_PROMPT

NEW_ENTERPRISE_PROMPT_CONTENT = ENTERPRISE_PROMPT


async def update_existing_prompts(db: AsyncSession) -> None:
    """Keep legacy prompt tables stable; do not overwrite edited prompt content."""
    await ensure_default_agent_prompts(db)
    logger.info("Skipped legacy prompt overwrite; DB prompt content is authoritative")


async def ensure_processing_column(db: AsyncSession) -> None:
    """无痛迁移：给 agent_conversations 表加 processing 列。"""
    try:
        await db.execute(text(
            "ALTER TABLE agent_conversations ADD COLUMN IF NOT EXISTS processing "
            "BOOLEAN DEFAULT FALSE"
        ))
        await db.commit()
        logger.info("Migration: ensured processing column on agent_conversations")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: processing column check failed: %s", e)


async def ensure_context_vars_column(db: AsyncSession) -> None:
    """无痛迁移：给 agent_conversations 表加 context_vars 列。"""
    try:
        await db.execute(text(
            "ALTER TABLE agent_conversations ADD COLUMN IF NOT EXISTS context_vars "
            "JSON DEFAULT '{}'"
        ))
        await db.commit()
        logger.info("Migration: ensured context_vars column on agent_conversations")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: context_vars column check failed: %s", e)


async def ensure_thinking_level_table(db: AsyncSession) -> None:
    """无痛创建 agent_thinking_levels 表。"""
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_thinking_levels ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  owner_id INTEGER NOT NULL,"
            "  conversation_id BIGINT NOT NULL,"
            "  query_text TEXT NOT NULL,"
            "  thinking_level VARCHAR(16) NOT NULL,"
            "  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,"
            "  source VARCHAR(16) NOT NULL DEFAULT 'rule',"
            "  reason TEXT DEFAULT '',"
            "  accepted BOOLEAN,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agent_thinking_levels_owner_id ON agent_thinking_levels(owner_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agent_thinking_levels_conversation_id ON agent_thinking_levels(conversation_id)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_thinking_levels table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: thinking level table check failed: %s", e)


async def ensure_thinking_level_signal_table(db: AsyncSession) -> None:
    """无痛创建思考等级隐式反馈信号表。"""
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_thinking_level_signals ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  thinking_level_id BIGINT REFERENCES agent_thinking_levels(id) ON DELETE SET NULL,"
            "  owner_id INTEGER NOT NULL,"
            "  conversation_id BIGINT NOT NULL,"
            "  query_text TEXT NOT NULL,"
            "  thinking_level VARCHAR(16) NOT NULL,"
            "  signal_type VARCHAR(32) NOT NULL,"
            "  signal_value DOUBLE PRECISION NOT NULL DEFAULT 0.0,"
            "  score_delta DOUBLE PRECISION NOT NULL DEFAULT 0.0,"
            "  reason TEXT DEFAULT '',"
            "  metadata JSONB DEFAULT '{}'::jsonb,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agent_thinking_signals_owner_id ON agent_thinking_level_signals(owner_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agent_thinking_signals_conversation_id ON agent_thinking_level_signals(conversation_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agent_thinking_signals_level ON agent_thinking_level_signals(thinking_level)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_thinking_level_signals table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: thinking level signal table check failed: %s", e)


async def ensure_event_table(db: AsyncSession) -> None:
    """引擎事件表迁移：create_all 兜 ALTER ADD COLUMN IF NOT EXISTS。"""
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_events ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  conversation_id BIGINT NOT NULL,"
            "  event_type VARCHAR(32) NOT NULL,"
            "  payload JSONB DEFAULT '{}'::jsonb,"
            "  llm_response_id VARCHAR(64),"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agent_events_conversation_id ON agent_events(conversation_id)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_events table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: agent_events table check failed: %s", e)


async def ensure_migrated_tables(db: AsyncSession) -> None:
    """Ensure 3 tables migrated from framework exist (idempotent)."""
    try:
        from sqlalchemy import text as _text
        agent_config_sql = """
            CREATE TABLE IF NOT EXISTS agent_configs (
                id BIGSERIAL PRIMARY KEY, agent_code VARCHAR(64) NOT NULL UNIQUE,
                agent_name VARCHAR(128) DEFAULT '', provider VARCHAR(64) DEFAULT '',
                model VARCHAR(64) DEFAULT '', system_prompt TEXT DEFAULT '',
                purpose VARCHAR(256) DEFAULT '', enabled BOOLEAN DEFAULT TRUE,
                temperature DOUBLE PRECISION, top_p DOUBLE PRECISION,
                max_tokens INTEGER, timeout_ms INTEGER,
                fallback_model VARCHAR(64), fallback_enabled BOOLEAN DEFAULT FALSE,
                max_concurrency INTEGER, cooldown_seconds INTEGER,
                retry_count INTEGER DEFAULT 3, daily_call_limit INTEGER,
                daily_budget DOUBLE PRECISION, monthly_budget DOUBLE PRECISION,
                response_format VARCHAR(16) DEFAULT 'text',
                log_prompt_enabled BOOLEAN DEFAULT TRUE,
                log_response_enabled BOOLEAN DEFAULT TRUE,
                sensitive_action_policy VARCHAR(16) DEFAULT 'confirm',
                updated_by INTEGER,
                created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """
        approval_queue_sql = """
            CREATE TABLE IF NOT EXISTS agent_approval_queue (
                id BIGSERIAL PRIMARY KEY, agent_code VARCHAR(64) DEFAULT '',
                tool_name VARCHAR(128) NOT NULL, tool_args TEXT,
                status VARCHAR(16) DEFAULT 'pending', requested_by INTEGER NOT NULL,
                decided_by INTEGER, conversation_id BIGINT, reason TEXT,
                decided_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """
        usage_daily_sql = """
            CREATE TABLE IF NOT EXISTS agent_usage_daily (
                id BIGSERIAL PRIMARY KEY, usage_date DATE NOT NULL,
                model_key VARCHAR(64) NOT NULL, provider VARCHAR(32) DEFAULT '',
                module VARCHAR(64) DEFAULT '', call_count INTEGER DEFAULT 0,
                prompt_tokens BIGINT DEFAULT 0, completion_tokens BIGINT DEFAULT 0,
                cost DOUBLE PRECISION DEFAULT 0.0,
                created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """
        for sql in [agent_config_sql, approval_queue_sql, usage_daily_sql]:
            await db.execute(_text(sql))
        await db.execute(_text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_usage_daily "
            "ON agent_usage_daily (usage_date, model_key, provider, module)"
        ))
        await db.commit()
        logger.info("Migration: ensured all 3 migrated agent tables")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: migrated tables check failed: %s", e)


async def ensure_snapshot_table(db: AsyncSession) -> None:
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_context_snapshots ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  conversation_id BIGINT NOT NULL,"
            "  snapshot_type VARCHAR(32) NOT NULL,"
            "  event_id_before BIGINT,"
            "  event_id_after BIGINT,"
            "  message_count_before INTEGER DEFAULT 0,"
            "  message_count_after INTEGER DEFAULT 0,"
            "  token_estimate_before INTEGER DEFAULT 0,"
            "  token_estimate_after INTEGER DEFAULT 0,"
            "  summary TEXT,"
            "  snapshot_data JSONB,"
            "  compression_ratio DOUBLE PRECISION,"
            "  restored_from BIGINT,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_snapshots_conv ON agent_context_snapshots(conversation_id)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_context_snapshots table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: snapshot table check failed: %s", e)


async def ensure_message_meta_usage_column(db: AsyncSession) -> None:
    """无痛迁移：给 agent_message_meta 表加 usage 列。"""
    try:
        await db.execute(text(
            "ALTER TABLE agent_message_meta ADD COLUMN IF NOT EXISTS usage JSON DEFAULT NULL"
        ))
        await db.commit()
        logger.info("Migration: ensured usage column on agent_message_meta")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: usage column check failed: %s", e)


async def ensure_message_status_column(db: AsyncSession) -> None:
    """无痛迁移：给 agent_messages 表加 status/edited_from_message_id/branch_root_message_id 列。"""
    try:
        await db.execute(text(
            "ALTER TABLE agent_messages ADD COLUMN IF NOT EXISTS status "
            "VARCHAR(16) DEFAULT 'active'"
        ))
        await db.execute(text(
            "ALTER TABLE agent_messages ADD COLUMN IF NOT EXISTS edited_from_message_id "
            "BIGINT DEFAULT NULL"
        ))
        await db.execute(text(
            "ALTER TABLE agent_messages ADD COLUMN IF NOT EXISTS branch_root_message_id "
            "BIGINT DEFAULT NULL"
        ))
        await db.commit()
        logger.info("Migration: ensured status/edited_from/branch_root columns on agent_messages")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: message status columns check failed: %s", e)


async def ensure_trajectory_table(db: AsyncSession) -> None:
    """Create agent_trajectory_records table (idempotent)."""
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_trajectory_records ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  conversation_id BIGINT NOT NULL,"
            "  owner_id INTEGER NOT NULL,"
            "  session_id VARCHAR(64) NOT NULL,"
            "  turn_index INTEGER DEFAULT 0,"
            "  user_input TEXT DEFAULT '',"
            "  tool_calls JSONB DEFAULT '[]'::jsonb,"
            "  tool_results JSONB DEFAULT '[]'::jsonb,"
            "  assistant_response TEXT,"
            "  user_correction TEXT,"
            "  failure_recovery JSONB,"
            "  thinking_level VARCHAR(16),"
            "  profile_signals JSONB DEFAULT '[]'::jsonb,"
            "  error_occurred BOOLEAN DEFAULT FALSE,"
            "  duration_ms DOUBLE PRECISION,"
            "  token_count INTEGER,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_trajectory_conv ON agent_trajectory_records(conversation_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_trajectory_session ON agent_trajectory_records(session_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_trajectory_owner ON agent_trajectory_records(owner_id)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_trajectory_records table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: trajectory table check failed: %s", e)


async def ensure_profile_v2_tables(db: AsyncSession) -> None:
    """Create profile 2.0 tables (role/enterprise/market/signals)."""
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_role_profiles ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  role_key VARCHAR(64) NOT NULL UNIQUE,"
            "  role_name VARCHAR(128) DEFAULT '',"
            "  description TEXT DEFAULT '',"
            "  tone TEXT,"
            "  taboos JSONB DEFAULT '[]'::jsonb,"
            "  focus_areas JSONB DEFAULT '[]'::jsonb,"
            "  habits JSONB DEFAULT '[]'::jsonb,"
            "  allowed_tools JSONB DEFAULT '[]'::jsonb,"
            "  priority INTEGER DEFAULT 0,"
            "  enabled BOOLEAN DEFAULT TRUE,"
            "  version INTEGER DEFAULT 1,"
            "  updated_by INTEGER,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_enterprise_profiles ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  enterprise_key VARCHAR(64) NOT NULL UNIQUE DEFAULT 'default',"
            "  enterprise_name VARCHAR(256) DEFAULT '',"
            "  description TEXT DEFAULT '',"
            "  tone TEXT,"
            "  taboos JSONB DEFAULT '[]'::jsonb,"
            "  focus_areas JSONB DEFAULT '[]'::jsonb,"
            "  business_rules JSONB DEFAULT '[]'::jsonb,"
            "  communication_style TEXT,"
            "  version INTEGER DEFAULT 1,"
            "  updated_by INTEGER,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_market_profiles ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  profile_type VARCHAR(32) NOT NULL,"
            "  key VARCHAR(128) NOT NULL,"
            "  name VARCHAR(256) DEFAULT '',"
            "  description TEXT DEFAULT '',"
            "  attributes JSONB DEFAULT '{}'::jsonb,"
            "  tags JSONB DEFAULT '[]'::jsonb,"
            "  enabled BOOLEAN DEFAULT TRUE,"
            "  priority INTEGER DEFAULT 0,"
            "  version INTEGER DEFAULT 1,"
            "  updated_by INTEGER,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_profile_signals ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  owner_id INTEGER NOT NULL,"
            "  signal_type VARCHAR(32) NOT NULL,"
            "  target_profile_type VARCHAR(32) DEFAULT 'user',"
            "  signal_data JSONB DEFAULT '{}'::jsonb,"
            "  confidence DOUBLE PRECISION DEFAULT 0.0,"
            "  source VARCHAR(32) DEFAULT 'auto',"
            "  conversation_id BIGINT,"
            "  applied BOOLEAN DEFAULT FALSE,"
            "  applied_at TIMESTAMPTZ,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_profile_signals_owner ON agent_profile_signals(owner_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_profile_signals_type ON agent_profile_signals(signal_type)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_market_profiles_type ON agent_market_profiles(profile_type)"
        ))
        await db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_market_profiles_key ON agent_market_profiles(profile_type, key)"
        ))
        await db.commit()
        logger.info("Migration: ensured profile 2.0 tables")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: profile 2.0 tables check failed: %s", e)


async def ensure_trajectory_unique_constraint(db: AsyncSession) -> None:
    """Create unique index on agent_trajectory_records (conversation_id, turn_index).

    PostgreSQL 17 does not support ``ADD CONSTRAINT IF NOT EXISTS``, so we
    use a unique index (which supports ``IF NOT EXISTS``) as the durable
    uniqueness enforcement. This also doubles as a query index for
    trajectory lookups by conversation.
    """
    try:
        # Drop any orphan constraint from the previous flawed migration
        await db.execute(text(
            "ALTER TABLE agent_trajectory_records "
            "DROP CONSTRAINT IF EXISTS uq_trajectory_conv_turn"
        ))
        await db.commit()
    except Exception:
        await db.rollback()
    try:
        await db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_trajectory_conv_turn "
            "ON agent_trajectory_records (conversation_id, turn_index)"
        ))
        await db.commit()
        logger.info("Migration: ensured uq_trajectory_conv_turn unique index")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: uq_trajectory_conv_turn index failed: %s", e)


async def ensure_checkpoint_table(db: AsyncSession) -> None:
    """Create agent_checkpoints table (idempotent)."""
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_checkpoints ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  conversation_id BIGINT NOT NULL,"
            "  owner_id INTEGER NOT NULL,"
            "  checkpoint_id VARCHAR(64) NOT NULL,"
            "  parent_checkpoint_id VARCHAR(64),"
            "  step INTEGER NOT NULL DEFAULT 0,"
            "  channel_values JSONB NOT NULL DEFAULT '{}'::jsonb,"
            "  extra_meta JSONB DEFAULT '{}'::jsonb,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW(),"
            "  CONSTRAINT uq_agent_checkpoints_conv_checkpoint UNIQUE (conversation_id, checkpoint_id)"
            ")"
        ))
        for sql in (
            "ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS checkpoint_id VARCHAR(64)",
            "ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS parent_checkpoint_id VARCHAR(64)",
            "ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS step INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS channel_values JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS extra_meta JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS workflow_run_id BIGINT",
            "ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS workflow_step_id BIGINT",
            "ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS agent_run_id VARCHAR(128)",
            "ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS checkpoint_type VARCHAR(32)",
            "ALTER TABLE agent_checkpoints ADD COLUMN IF NOT EXISTS resume_cursor JSONB DEFAULT '{}'::jsonb",
        ):
            await db.execute(text(sql))
        await db.execute(text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'agent_checkpoints'
                      AND column_name = 'checkpoint_type'
                      AND is_nullable = 'NO'
                ) THEN
                    ALTER TABLE agent_checkpoints ALTER COLUMN checkpoint_type DROP NOT NULL;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = 'agent_checkpoints'
                      AND constraint_name = 'uq_agent_checkpoints_conv_checkpoint'
                ) THEN
                    ALTER TABLE agent_checkpoints
                    ADD CONSTRAINT uq_agent_checkpoints_conv_checkpoint
                    UNIQUE (conversation_id, checkpoint_id);
                END IF;
            END $$;
            """
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_checkpoints_conv ON agent_checkpoints(conversation_id)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_checkpoints table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: checkpoint table check failed: %s", e)


async def ensure_workflow_tables(db: AsyncSession) -> None:
    """Create Agent user workflow ledger tables and extension columns."""
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_workflow_runs (
                id BIGSERIAL PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                creator_id INTEGER,
                source VARCHAR(32) NOT NULL DEFAULT 'manual',
                title VARCHAR(256) NOT NULL DEFAULT '',
                intent TEXT NOT NULL DEFAULT '',
                status VARCHAR(32) NOT NULL DEFAULT 'waiting',
                terminal_status VARCHAR(32),
                verification_status VARCHAR(32) NOT NULL DEFAULT 'pending',
                current_step_id BIGINT,
                progress_summary TEXT NOT NULL DEFAULT '',
                developer_summary TEXT,
                dirty_worktree_state JSONB,
                release_gate_verdict VARCHAR(64),
                queue_task_ids JSONB DEFAULT '[]'::jsonb,
                artifact_summary JSONB DEFAULT '{}'::jsonb,
                extra_meta JSONB DEFAULT '{}'::jsonb,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_workflow_steps (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL,
                step_key VARCHAR(128) NOT NULL DEFAULT '',
                title VARCHAR(256) NOT NULL DEFAULT '',
                type VARCHAR(32) NOT NULL DEFAULT 'agent',
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                order_index INTEGER NOT NULL DEFAULT 0,
                input_ref JSONB,
                output_ref JSONB,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 0,
                error_class VARCHAR(128),
                error_signature VARCHAR(256),
                summary TEXT,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                extra_meta JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_tool_calls (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL,
                step_id BIGINT,
                agent_run_id VARCHAR(128),
                tool_name VARCHAR(128) NOT NULL,
                target_module VARCHAR(64),
                action VARCHAR(128),
                caller VARCHAR(128),
                arguments_ref JSONB,
                arguments_hash VARCHAR(64) NOT NULL DEFAULT '',
                side_effect_level VARCHAR(32) NOT NULL DEFAULT 'readonly',
                approval_policy VARCHAR(32) NOT NULL DEFAULT 'auto',
                status VARCHAR(32) NOT NULL DEFAULT 'planned',
                idempotency_key VARCHAR(128),
                result_ref JSONB,
                error_class VARCHAR(128),
                error_signature VARCHAR(256),
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                extra_meta JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_workflow_artifacts (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL,
                step_id BIGINT,
                artifact_type VARCHAR(32) NOT NULL,
                storage_kind VARCHAR(32) NOT NULL,
                storage_ref JSONB,
                visibility VARCHAR(32) NOT NULL DEFAULT 'user',
                lifecycle VARCHAR(32) NOT NULL DEFAULT 'candidate',
                ttl_seconds INTEGER,
                checksum VARCHAR(128),
                summary TEXT,
                extra_meta JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_verification_results (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL,
                step_id BIGINT,
                verification_type VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL,
                command_or_capability TEXT,
                evidence_ref JSONB,
                summary TEXT,
                is_required_for_completion BOOLEAN NOT NULL DEFAULT TRUE,
                duration_ms INTEGER,
                extra_meta JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_failure_records (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL,
                step_id BIGINT,
                tool_call_id BIGINT,
                failure_type VARCHAR(32) NOT NULL,
                error_signature VARCHAR(256),
                retryable BOOLEAN NOT NULL DEFAULT FALSE,
                retry_count INTEGER NOT NULL DEFAULT 0,
                next_action VARCHAR(32) NOT NULL DEFAULT 'manual',
                evidence_ref JSONB,
                handoff_note TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        for sql in (
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS owner_id INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS creator_id INTEGER",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'manual'",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS title VARCHAR(256) NOT NULL DEFAULT ''",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS intent TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'waiting'",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS terminal_status VARCHAR(32)",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS verification_status VARCHAR(32) NOT NULL DEFAULT 'pending'",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS current_step_id BIGINT",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS progress_summary TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS developer_summary TEXT",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS dirty_worktree_state JSONB",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS release_gate_verdict VARCHAR(64)",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS queue_task_ids JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS artifact_summary JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS extra_meta JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_workflow_runs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS run_id BIGINT NOT NULL DEFAULT 0",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS step_key VARCHAR(128) NOT NULL DEFAULT ''",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS title VARCHAR(256) NOT NULL DEFAULT ''",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS type VARCHAR(32) NOT NULL DEFAULT 'agent'",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'pending'",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS order_index INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS input_ref JSONB",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS output_ref JSONB",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS max_retries INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS error_class VARCHAR(128)",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS error_signature VARCHAR(256)",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS summary TEXT",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS extra_meta JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_workflow_steps ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS run_id BIGINT NOT NULL DEFAULT 0",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS step_id BIGINT",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS agent_run_id VARCHAR(128)",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS tool_name VARCHAR(128) NOT NULL DEFAULT ''",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS target_module VARCHAR(64)",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS action VARCHAR(128)",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS caller VARCHAR(128)",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS arguments_ref JSONB",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS arguments_hash VARCHAR(64) NOT NULL DEFAULT ''",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS side_effect_level VARCHAR(32) NOT NULL DEFAULT 'readonly'",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS approval_policy VARCHAR(32) NOT NULL DEFAULT 'auto'",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'planned'",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128)",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS result_ref JSONB",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS error_class VARCHAR(128)",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS error_signature VARCHAR(256)",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS extra_meta JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_tool_calls ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS run_id BIGINT NOT NULL DEFAULT 0",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS step_id BIGINT",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS artifact_type VARCHAR(32) NOT NULL DEFAULT ''",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS storage_kind VARCHAR(32) NOT NULL DEFAULT ''",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS storage_ref JSONB",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS visibility VARCHAR(32) NOT NULL DEFAULT 'user'",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS lifecycle VARCHAR(32) NOT NULL DEFAULT 'candidate'",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS ttl_seconds INTEGER",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS checksum VARCHAR(128)",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS summary TEXT",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS extra_meta JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_workflow_artifacts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS run_id BIGINT NOT NULL DEFAULT 0",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS step_id BIGINT",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS verification_type VARCHAR(32) NOT NULL DEFAULT ''",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT ''",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS command_or_capability TEXT",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS evidence_ref JSONB",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS summary TEXT",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS is_required_for_completion BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS duration_ms INTEGER",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS extra_meta JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_verification_results ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS run_id BIGINT NOT NULL DEFAULT 0",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS step_id BIGINT",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS tool_call_id BIGINT",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS failure_type VARCHAR(32) NOT NULL DEFAULT ''",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS error_signature VARCHAR(256)",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS retryable BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS next_action VARCHAR(32) NOT NULL DEFAULT 'manual'",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS evidence_ref JSONB",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS handoff_note TEXT",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE agent_failure_records ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        ):
            await db.execute(text(sql))
        for sql in (
            "CREATE INDEX IF NOT EXISTS ix_agent_workflow_runs_owner ON agent_workflow_runs(owner_id)",
            "CREATE INDEX IF NOT EXISTS ix_agent_workflow_runs_status ON agent_workflow_runs(status)",
            "CREATE INDEX IF NOT EXISTS ix_agent_workflow_steps_run ON agent_workflow_steps(run_id)",
            "CREATE INDEX IF NOT EXISTS ix_agent_tool_calls_run ON agent_tool_calls(run_id)",
            "CREATE INDEX IF NOT EXISTS ix_agent_tool_calls_step ON agent_tool_calls(step_id)",
            "CREATE INDEX IF NOT EXISTS ix_agent_tool_calls_idempotency ON agent_tool_calls(idempotency_key)",
            "CREATE INDEX IF NOT EXISTS ix_agent_workflow_artifacts_run ON agent_workflow_artifacts(run_id)",
            "CREATE INDEX IF NOT EXISTS ix_agent_verification_results_run ON agent_verification_results(run_id)",
            "CREATE INDEX IF NOT EXISTS ix_agent_failure_records_run ON agent_failure_records(run_id)",
        ):
            await db.execute(text(sql))
        for sql in (
            "ALTER TABLE agent_approval_queue ADD COLUMN IF NOT EXISTS workflow_run_id BIGINT",
            "ALTER TABLE agent_approval_queue ADD COLUMN IF NOT EXISTS workflow_step_id BIGINT",
            "ALTER TABLE agent_approval_queue ADD COLUMN IF NOT EXISTS tool_call_id BIGINT",
            "ALTER TABLE agent_approval_queue ADD COLUMN IF NOT EXISTS request_type VARCHAR(32)",
            "ALTER TABLE agent_approval_queue ADD COLUMN IF NOT EXISTS risk_level VARCHAR(32)",
            "ALTER TABLE agent_approval_queue ADD COLUMN IF NOT EXISTS decision_scope VARCHAR(32)",
            "ALTER TABLE agent_approval_queue ADD COLUMN IF NOT EXISTS payload_hash VARCHAR(64)",
            "ALTER TABLE agent_approval_queue ADD COLUMN IF NOT EXISTS resume_target JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE agent_approval_queue ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ",
            "CREATE INDEX IF NOT EXISTS ix_agent_approval_workflow_run ON agent_approval_queue(workflow_run_id)",
            "CREATE INDEX IF NOT EXISTS ix_agent_approval_tool_call ON agent_approval_queue(tool_call_id)",
        ):
            await db.execute(text(sql))
        await db.commit()
        logger.info("Migration: ensured agent workflow ledger tables")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: workflow ledger table check failed: %s", e)


async def ensure_skill_registry_table(db: AsyncSession) -> None:
    """Create skill governance tables (idempotent)."""
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_skill_registry ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  name VARCHAR(128) NOT NULL UNIQUE,"
            "  description TEXT DEFAULT '',"
            "  source VARCHAR(32) DEFAULT 'manual',"
            "  source_file VARCHAR(512),"
            "  body TEXT,"
            "  allowed_tools JSONB DEFAULT '[]'::jsonb,"
            "  paths JSONB DEFAULT '[]'::jsonb,"
            "  scope VARCHAR(32) DEFAULT 'global',"
            "  priority INTEGER DEFAULT 0,"
            "  enabled BOOLEAN DEFAULT TRUE,"
            "  approval_status VARCHAR(32) DEFAULT 'pending_approval',"
            "  created_by INTEGER,"
            "  updated_by INTEGER,"
            "  tags JSONB DEFAULT '[]'::jsonb,"
            "  category VARCHAR(64),"
            "  version INTEGER DEFAULT 1,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_skill_approvals ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  skill_name VARCHAR(128) NOT NULL,"
            "  operation VARCHAR(32) NOT NULL,"
            "  previous_state JSONB,"
            "  requested_state JSONB,"
            "  status VARCHAR(32) DEFAULT 'pending_approval',"
            "  requested_by INTEGER,"
            "  decided_by INTEGER,"
            "  decided_at TIMESTAMPTZ,"
            "  review_result_id BIGINT,"
            "  reason TEXT,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_skill_provenance ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  skill_name VARCHAR(128) NOT NULL,"
            "  event_type VARCHAR(32) NOT NULL,"
            "  source VARCHAR(32) DEFAULT '',"
            "  detail JSONB DEFAULT '{}'::jsonb,"
            "  actor_id INTEGER,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_skill_provenance_name ON agent_skill_provenance(skill_name)"
        ))
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_skill_usage ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  skill_name VARCHAR(128) NOT NULL,"
            "  conversation_id BIGINT,"
            "  owner_id INTEGER,"
            "  success BOOLEAN DEFAULT TRUE,"
            "  duration_ms DOUBLE PRECISION DEFAULT 0.0,"
            "  error_detail TEXT,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_skill_usage_name ON agent_skill_usage(skill_name)"
        ))
        # Migration: ensure tags/category/version columns on existing agent_skill_registry
        for col_sql in [
            "ALTER TABLE agent_skill_registry ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE agent_skill_registry ADD COLUMN IF NOT EXISTS category VARCHAR(64)",
            "ALTER TABLE agent_skill_registry ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1",
        ]:
            try:
                await db.execute(text(col_sql))
            except Exception:
                pass
        await db.commit()
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_review_tasks ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  conversation_id BIGINT NOT NULL,"
            "  owner_id INTEGER NOT NULL,"
            "  status VARCHAR(16) DEFAULT 'pending',"
            "  review_context JSONB DEFAULT '{}'::jsonb,"
            "  started_at TIMESTAMPTZ,"
            "  completed_at TIMESTAMPTZ,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_review_results ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  review_task_id BIGINT NOT NULL,"
            "  owner_id INTEGER NOT NULL,"
            "  result_type VARCHAR(32) NOT NULL,"
            "  title VARCHAR(256) DEFAULT '',"
            "  summary TEXT DEFAULT '',"
            "  detail JSONB DEFAULT '{}'::jsonb,"
            "  status VARCHAR(16) DEFAULT 'proposal',"
            "  reviewed_by INTEGER,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.commit()
        logger.info("Migration: ensured skill governance tables")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: skill governance tables check failed: %s", e)


async def ensure_tool_guide_tables(db: AsyncSession) -> None:
    """Create tool guidance control plane tables (idempotent)."""
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_tool_guides (
                id BIGSERIAL PRIMARY KEY,
                owner_id INTEGER,
                agent_code VARCHAR(64) NOT NULL DEFAULT 'default',
                tool_name VARCHAR(128) NOT NULL,
                scope VARCHAR(32) NOT NULL DEFAULT 'global',
                version INTEGER DEFAULT 1,
                title VARCHAR(256) DEFAULT '',
                guide_text TEXT DEFAULT '',
                failure_policy JSONB DEFAULT '{}'::jsonb,
                acceptance_policy JSONB DEFAULT '{}'::jsonb,
                enabled BOOLEAN DEFAULT TRUE,
                status VARCHAR(32) DEFAULT 'active',
                source VARCHAR(32) DEFAULT 'manual',
                created_by INTEGER,
                updated_by INTEGER,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_tool_guide_active
            ON agent_tool_guides (COALESCE(owner_id, 0), agent_code, tool_name, scope)
            WHERE status = 'active'
        """))
        await db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_tool_guides_owner
            ON agent_tool_guides(owner_id)
        """))
        await db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_tool_guides_tool
            ON agent_tool_guides(tool_name)
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_tool_guide_versions (
                id BIGSERIAL PRIMARY KEY,
                guide_id BIGINT NOT NULL,
                owner_id INTEGER,
                agent_code VARCHAR(64) NOT NULL DEFAULT 'default',
                tool_name VARCHAR(128) NOT NULL,
                scope VARCHAR(32) NOT NULL,
                version INTEGER NOT NULL,
                title VARCHAR(256) DEFAULT '',
                guide_text TEXT DEFAULT '',
                failure_policy JSONB DEFAULT '{}'::jsonb,
                acceptance_policy JSONB DEFAULT '{}'::jsonb,
                status VARCHAR(32) DEFAULT 'active',
                source VARCHAR(32) DEFAULT 'manual',
                created_by INTEGER,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_tool_guide_versions_guide
            ON agent_tool_guide_versions(guide_id)
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_tool_guide_candidates (
                id BIGSERIAL PRIMARY KEY,
                owner_id INTEGER,
                agent_code VARCHAR(64) NOT NULL DEFAULT 'default',
                tool_name VARCHAR(128) NOT NULL,
                scope VARCHAR(32) NOT NULL DEFAULT 'agent',
                title VARCHAR(256) DEFAULT '',
                guide_text TEXT DEFAULT '',
                failure_policy JSONB DEFAULT '{}'::jsonb,
                acceptance_policy JSONB DEFAULT '{}'::jsonb,
                status VARCHAR(32) DEFAULT 'draft',
                source VARCHAR(32) DEFAULT 'mined',
                source_trajectory_id BIGINT,
                proposed_by INTEGER,
                reviewed_by INTEGER,
                review_note TEXT,
                promoted_at TIMESTAMPTZ,
                promoted_guide_id BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_tool_guide_candidates_status
            ON agent_tool_guide_candidates(status)
        """))
        await db.commit()
        logger.info("Migration: ensured tool guidance control plane tables")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: tool guide tables check failed: %s", e)


async def ensure_default_tool_guides_seed(db: AsyncSession) -> None:
    """Seed default meta-tool guidance rows after tables exist."""
    try:
        from .services.tool_guidance_service import ensure_default_tool_guides

        await ensure_default_tool_guides(db)
        logger.info("Migration: ensured default tool guidance seeds")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: default tool guidance seeds failed: %s", e)


async def ensure_compaction_table(db: AsyncSession) -> None:
    """Create agent_context_compactions table and unique index (idempotent)."""
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_context_compactions (
                id BIGSERIAL PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                conversation_id BIGINT NOT NULL,
                until_event_id BIGINT NOT NULL,
                generation INTEGER NOT NULL DEFAULT 0,
                status VARCHAR(16) NOT NULL DEFAULT 'building',
                summary TEXT,
                folded_event_ids JSONB DEFAULT '[]'::jsonb,
                token_before INTEGER DEFAULT 0,
                token_after INTEGER DEFAULT 0,
                error TEXT,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_compactions_conv
            ON agent_context_compactions(conversation_id)
        """))
        await db.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_compactions_conv_until_gen
            ON agent_context_compactions(conversation_id, until_event_id, generation)
        """))
        await db.commit()
        logger.info("Migration: ensured agent_context_compactions table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: compaction table check failed: %s", e)


async def run_init(db: AsyncSession) -> None:
    """Agent 模块启动初始化入口。"""
    await ensure_migrated_tables(db)
    await ensure_timeline_column(db)
    await ensure_message_meta_usage_column(db)
    await ensure_processing_column(db)
    await ensure_context_vars_column(db)
    await ensure_thinking_level_table(db)
    await ensure_thinking_level_signal_table(db)
    await ensure_event_table(db)
    await ensure_snapshot_table(db)
    await ensure_message_status_column(db)
    await ensure_skill_registry_table(db)
    await ensure_trajectory_table(db)
    await ensure_trajectory_unique_constraint(db)
    await ensure_checkpoint_table(db)
    await ensure_workflow_tables(db)
    await ensure_profile_v2_tables(db)
    await ensure_tool_guide_tables(db)
    await ensure_default_tool_guides_seed(db)
    await ensure_compaction_table(db)
    await ensure_default_prompts(db)
    await ensure_default_agent_prompts(db)
    try:
        from .services.skill_governance_service import scan_file_skills_to_registry

        result = await scan_file_skills_to_registry(
            db,
            base_dir=os.environ.get("SKILLS_DIR", "data/skills"),
        )
        logger.info("Skill registry sync: %s", result)
    except Exception as exc:
        logger.warning("Skill registry sync failed (non-fatal): %s", exc)
