"""Agent 模块表初始化：确保三层提示词默认数据存在，并执行无痛迁移。"""
import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AgentEnterprisePrompt, AgentSystemPrompt, AgentUserProfile
from .models_prompt import AgentPrompt
from .prompt_seeds import (
    AGENT_PROMPT_SEEDS,
    ENTERPRISE_PROMPT,
    PROMPT_SCOPE_SYSTEM,
    SYSTEM_BASE_PROMPT,
)

logger = logging.getLogger("v2.agent").getChild("init_db")

DEFAULT_SYSTEM_PROMPT = SYSTEM_BASE_PROMPT

DEFAULT_ENTERPRISE_PROMPT = ENTERPRISE_PROMPT


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


async def ensure_checkpoint_table(db: AsyncSession) -> None:
    """Create agent_checkpoints table (idempotent)."""
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_checkpoints ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  conversation_id BIGINT NOT NULL,"
            "  owner_id INTEGER NOT NULL,"
            "  checkpoint_type VARCHAR(32) NOT NULL,"
            "  round_index INTEGER DEFAULT 0,"
            "  state_data JSONB DEFAULT '{}'::jsonb,"
            "  summary TEXT,"
            "  parent_id BIGINT,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_checkpoints_conv ON agent_checkpoints(conversation_id)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_checkpoints table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: checkpoint table check failed: %s", e)


async def ensure_workflow_recipes_table(db: AsyncSession) -> None:
    """Create agent_workflow_recipes table (idempotent)."""
    try:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS agent_workflow_recipes ("
            "  id BIGSERIAL PRIMARY KEY,"
            "  owner_id INTEGER NOT NULL,"
            "  name VARCHAR(256) DEFAULT '',"
            "  description TEXT DEFAULT '',"
            "  intent_label VARCHAR(128) DEFAULT '',"
            "  trigger_condition TEXT DEFAULT '',"
            "  steps JSONB DEFAULT '[]'::jsonb,"
            "  tools_used JSONB DEFAULT '[]'::jsonb,"
            "  status VARCHAR(16) DEFAULT 'proposal',"
            "  version INTEGER DEFAULT 1,"
            "  success_weight DOUBLE PRECISION DEFAULT 0.0,"
            "  fail_count INTEGER DEFAULT 0,"
            "  avg_duration_ms DOUBLE PRECISION,"
            "  avg_tool_count DOUBLE PRECISION,"
            "  last_used_at TIMESTAMPTZ,"
            "  confidence DOUBLE PRECISION DEFAULT 0.0,"
            "  source_conversation_id BIGINT,"
            "  source_trajectory_id BIGINT,"
            "  source_experience_id BIGINT,"
            "  enabled BOOLEAN DEFAULT TRUE,"
            "  created_at TIMESTAMPTZ DEFAULT NOW(),"
            "  updated_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_workflow_recipes_owner ON agent_workflow_recipes(owner_id)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_workflow_recipes table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: workflow_recipes table creation failed: %s", e)


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
    await ensure_checkpoint_table(db)
    await ensure_profile_v2_tables(db)
    await ensure_workflow_recipes_table(db)
    await ensure_default_prompts(db)
    await ensure_default_agent_prompts(db)
