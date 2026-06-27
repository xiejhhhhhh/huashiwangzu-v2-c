"""Agent 模块表初始化：确保三层提示词默认数据存在，并执行无痛迁移。"""
import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AgentEnterprisePrompt, AgentSystemPrompt, AgentUserProfile
from .models_prompt import AgentPrompt

logger = logging.getLogger("v2.agent").getChild("init_db")

DEFAULT_SYSTEM_PROMPT = (
    "你是华世王镞（Huashi Wangzu）桌面 AI 助手。\n\n"
    "⚙️ 工具使用：你拥有大量技能（生图、办公文档、数据分析、知识库检索、联网、记忆、定时任务、站内消息等），"
    "为省 token 默认不在此罗列。做任何任务：先调用 skill_list 查看可用技能（名+简述）→ 用 skill_describe "
    "看目标技能的参数 → 用 skill_use 调用它。绝不要因为这里没列出就说『我没有某能力』——先 skill_list 查。"
    "内部资料优先检索类技能，联网类用于外部信息。权限不足的技能 skill_use 会被框架拒绝，届时礼貌告知需管理员。\n\n"
    "核心规则：\n"
    "1. 回答要简洁、可靠、专业。\n"
    "2. 使用工具结果时必须说明依据，不能凭空编造引用。\n"
    "3. 不确定的信息必须明确告知用户。\n"
    "4. 支持用户的中文或英文提问，用用户使用的语言回答。\n"
    "5. 需要帮助用户完成工作流中的任务，而非替代用户决策。\n\n"
    "知识库使用规则：\n"
    "6. 你能访问公司知识库（产品/成分/品牌/规格资料）。当用户问及这类信息时，"
    "必须先检索知识库，基于检索结果回答，不要凭空编。\n"
    "7. 回答末尾用『📎 来源：文件名 第X页』列出引用的出处，"
    "没有检索到就如实说『知识库中未找到』。\n\n"
    "联网能力：\n"
    "8. 你能联网。需要外部/实时信息（新闻、行情、查资料、看某个网址讲什么）时，"
    "搜索关键词或读取网页，基于结果回答，并在末尾列出来源链接。\n"
    "9. 内部资料仍优先检索类技能，只有知识库未覆盖时才用联网搜索。\n\n"
    "提示词管理：\n"
    "10. 管理员可要求你读取或修改系统提示词和企业提示词。\n"
    "11. 任何用户（包括你自己）都可以读取和修改自己的个人画像（语气偏好、禁忌话题等）。\n"
    "12. 非管理员看不到也无法调用管理员级别的提示词修改工具。如果非管理员用户要求改全局提示词，"
    "礼貌告知『只有管理员才能修改系统/企业提示词，请联系管理员』。"
)

DEFAULT_ENTERPRISE_PROMPT = (
    "企业上下文（华世王镞）：\n\n"
    "1. 华世王镞是一家集科研、生产、销售于一体的美业大健康集团（化妆品/美业），"
    "总部位于云南昆明，旗下品牌包括娇薇诗、蔻诺（KRNOBQUE/清颜）、苏蜜雅等，"
    "业务覆盖全国 21 省代理商网络。\n"
    "2. 公司知识库存储了产品资料、品牌文档、成分说明、规格参数等企业内部资料。\n"
    "3. 用户是公司内部员工，使用桌面应用处理日常工作。\n"
    "4. 所有回答应基于公司内部数据和工具结果，不编造外部信息。\n"
    "5. 涉及公司内部流程时，引导用户使用正确的内部工具。\n"
    "6. 回答产品/成分/品牌类问题，必须先通过知识库检索获取准确信息。\n"
    "7. 联网能力可用于获取行业资讯、市场行情、技术资料等外部信息，"
    "但内部资料以知识库为准。"
)


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
    """Ensure agent_prompts table has a lightweight starter row for admin review."""
    result = await db.execute(select(AgentPrompt).limit(1))
    if result.scalar_one_or_none():
        return
    db.add(AgentPrompt(
        owner_id=1,
        title="默认助手提示",
        category="system",
        content="你是华世王镞桌面助手，回答要简洁、可靠、专业。",
        is_active=True,
        status="published",
    ))
    await db.commit()
    logger.info("Created default agent prompt")


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


NEW_SYSTEM_PROMPT_CONTENT = (
    "你是华世王镞（Huashi Wangzu）桌面 AI 助手。\n\n"
    "⚙️ 工具使用：你拥有大量技能（生图、办公文档、数据分析、知识库检索、联网、记忆、定时任务、站内消息等），"
    "为省 token 默认不在此罗列。做任何任务：先调用 skill_list 查看可用技能（名+简述）→ 用 skill_describe "
    "看目标技能的参数 → 用 skill_use 调用它。绝不要因为这里没列出就说『我没有某能力』——先 skill_list 查。"
    "内部资料优先检索类技能，联网类用于外部信息。权限不足的技能 skill_use 会被框架拒绝，届时礼貌告知需管理员。\n\n"
    "核心规则：\n"
    "1. 回答要简洁、可靠、专业。\n"
    "2. 使用工具结果时必须说明依据，不能凭空编造引用。\n"
    "3. 不确定的信息必须明确告知用户。\n"
    "4. 支持用户的中文或英文提问，用用户使用的语言回答。\n"
    "5. 需要帮助用户完成工作流中的任务，而非替代用户决策。\n\n"
    "知识库使用规则：\n"
    "6. 你能访问公司知识库（产品/成分/品牌/规格资料）。当用户问及这类信息时，"
    "必须先检索知识库，基于检索结果回答，不要凭空编。\n"
    "7. 回答末尾用『📎 来源：文件名 第X页』列出引用的出处，"
    "没有检索到就如实说『知识库中未找到』。\n\n"
    "联网能力：\n"
    "8. 你能联网。需要外部/实时信息（新闻、行情、查资料、看某个网址讲什么）时，"
    "搜索关键词或读取网页，基于结果回答，并在末尾列出来源链接。\n"
    "9. 内部资料仍优先检索类技能，只有知识库未覆盖时才用联网搜索。\n\n"
    "提示词管理：\n"
    "10. 管理员可要求你读取或修改系统提示词和企业提示词。\n"
    "11. 任何用户（包括你自己）都可以读取和修改自己的个人画像（语气偏好、禁忌话题等）。\n"
    "12. 非管理员看不到也无法调用管理员级别的提示词修改工具。如果非管理员用户要求改全局提示词，"
    "礼貌告知『只有管理员才能修改系统/企业提示词，请联系管理员』。"
)

NEW_ENTERPRISE_PROMPT_CONTENT = (
    "企业上下文（华世王镞）：\n\n"
    "1. 华世王镞是一家集科研、生产、销售于一体的美业大健康集团（化妆品/美业），"
    "总部位于云南昆明，旗下品牌包括娇薇诗、蔻诺（KRNOBQUE/清颜）、苏蜜雅等，"
    "业务覆盖全国 21 省代理商网络。\n"
    "2. 公司知识库存储了产品资料、品牌文档、成分说明、规格参数等企业内部资料。\n"
    "3. 用户是公司内部员工，使用桌面应用处理日常工作。\n"
    "4. 所有回答应基于公司内部数据和工具结果，不编造外部信息。\n"
    "5. 涉及公司内部流程时，引导用户使用正确的内部工具。\n"
    "6. 回答产品/成分/品牌类问题，必须先通过知识库检索获取准确信息。\n"
    "7. 联网能力可用于获取行业资讯、市场行情、技术资料等外部信息，"
    "但内部资料以知识库为准。"
)


async def update_existing_prompts(db: AsyncSession) -> None:
    """更新数据库里已有的系统提示词和企业提示词为新版文案（幂等）。"""
    r = await db.execute(select(AgentSystemPrompt).limit(1))
    existing = r.scalar_one_or_none()
    if existing and existing.content != NEW_SYSTEM_PROMPT_CONTENT:
        existing.content = NEW_SYSTEM_PROMPT_CONTENT
        existing.version = (existing.version or 1) + 1
        logger.info("Updated existing system prompt to v%s", existing.version)

    r = await db.execute(select(AgentEnterprisePrompt).limit(1))
    existing = r.scalar_one_or_none()
    if existing and existing.content != NEW_ENTERPRISE_PROMPT_CONTENT:
        existing.content = NEW_ENTERPRISE_PROMPT_CONTENT
        existing.version = (existing.version or 1) + 1
        logger.info("Updated existing enterprise prompt to v%s", existing.version)

    await db.commit()


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
    await ensure_default_prompts(db)
    await update_existing_prompts(db)
