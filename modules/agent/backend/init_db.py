"""Agent 模块表初始化：确保三层提示词默认数据存在，并执行无痛迁移。"""
import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from .models import AgentSystemPrompt, AgentEnterprisePrompt, AgentUserProfile, AgentConfig, ApprovalQueue, AgentUsageDaily, ContextSnapshot
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


async def ensure_event_table(db: AsyncSession) -> None:
    """引擎事件表迁移：create_all 兜 ALTER ADD COLUMN IF NOT EXISTS。"""
    from sqlalchemy import text
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


async def ensure_agent_state_tables(db: AsyncSession) -> None:
    """Ensure the 5 agent state tables exist (idempotent CREATE TABLE IF NOT EXISTS)."""
    tables = [
        """
        CREATE TABLE IF NOT EXISTS agent_hook_runs (
            id BIGSERIAL PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            conversation_id BIGINT,
            hook_name VARCHAR(128) NOT NULL,
            success BOOLEAN NOT NULL,
            duration_ms DOUBLE PRECISION NOT NULL,
            detail TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_recall_qualities (
            id BIGSERIAL PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            conversation_id BIGINT,
            query TEXT NOT NULL,
            layer VARCHAR(32) NOT NULL,
            limit_val INTEGER NOT NULL,
            total_results INTEGER NOT NULL,
            avg_similarity DOUBLE PRECISION NOT NULL,
            avg_confidence DOUBLE PRECISION NOT NULL,
            result_ids JSONB DEFAULT '[]'::jsonb,
            source_types JSONB,
            duration_ms DOUBLE PRECISION DEFAULT 0.0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_budget_states (
            id BIGSERIAL PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            conversation_id BIGINT NOT NULL UNIQUE,
            rounds_data JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_stuck_rounds (
            id BIGSERIAL PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            conversation_id BIGINT NOT NULL UNIQUE,
            rounds_data JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_failure_diagnostics (
            id BIGSERIAL PRIMARY KEY,
            owner_id INTEGER,
            conversation_id BIGINT,
            source VARCHAR(32) NOT NULL,
            operation VARCHAR(64) NOT NULL,
            error_type VARCHAR(64) NOT NULL,
            error_message TEXT NOT NULL,
            extra_data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
    ]
    indexes = [
        "CREATE INDEX IF NOT EXISTS ix_agent_hook_runs_owner_id ON agent_hook_runs(owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_agent_recall_qualities_owner_id ON agent_recall_qualities(owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_agent_budget_states_owner_id ON agent_budget_states(owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_agent_budget_states_conversation_id ON agent_budget_states(conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_agent_stuck_rounds_owner_id ON agent_stuck_rounds(owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_agent_stuck_rounds_conversation_id ON agent_stuck_rounds(conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_agent_failure_diagnostics_owner_id ON agent_failure_diagnostics(owner_id)",
    ]
    try:
        for sql in tables + indexes:
            await db.execute(text(sql))
        await db.commit()
        logger.info("Migration: ensured all 5 agent state tables")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: agent state tables check failed: %s", e)


async def ensure_maintenance_state_table(db: AsyncSession) -> None:
    """Ensure the cross-worker hook lifecycle state table exists (idempotent)."""
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_maintenance_state (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                maintenance_status VARCHAR(16) DEFAULT 'stopped',
                worker_id VARCHAR(64) DEFAULT '',
                started_at TIMESTAMPTZ,
                last_heartbeat_at TIMESTAMPTZ,
                run_count INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        # Seed the single row if missing
        await db.execute(text("""
            INSERT INTO agent_maintenance_state (id, maintenance_status, worker_id, run_count)
            VALUES (1, 'stopped', '', 0)
            ON CONFLICT (id) DO NOTHING
        """))
        await db.commit()
        logger.info("Migration: ensured agent_maintenance_state table + seed row")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: agent_maintenance_state table check failed: %s", e)


async def ensure_review_governance_tables(db: AsyncSession) -> None:
    """Ensure review + skill governance tables exist (idempotent)."""
    tables = [
        """
        CREATE TABLE IF NOT EXISTS agent_review_tasks (
            id BIGSERIAL PRIMARY KEY,
            conversation_id BIGINT NOT NULL,
            owner_id INTEGER NOT NULL,
            status VARCHAR(16) DEFAULT 'pending',
            review_context JSONB,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_review_results (
            id BIGSERIAL PRIMARY KEY,
            review_task_id BIGINT NOT NULL,
            owner_id INTEGER NOT NULL,
            result_type VARCHAR(32) NOT NULL,
            title VARCHAR(256) DEFAULT '',
            summary TEXT DEFAULT '',
            detail JSONB,
            status VARCHAR(16) DEFAULT 'proposal',
            reviewed_by INTEGER,
            reviewed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_skill_registry (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(128) NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            source VARCHAR(32) DEFAULT 'file_scan',
            source_file TEXT,
            body TEXT DEFAULT '',
            allowed_tools JSONB,
            paths JSONB,
            scope VARCHAR(32) DEFAULT 'global',
            priority INTEGER DEFAULT 0,
            enabled BOOLEAN DEFAULT TRUE,
            approval_status VARCHAR(16) DEFAULT 'pending_approval',
            created_by INTEGER,
            updated_by INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_skill_approvals (
            id BIGSERIAL PRIMARY KEY,
            skill_name VARCHAR(128) NOT NULL,
            operation VARCHAR(16) NOT NULL,
            previous_state JSONB,
            requested_state JSONB,
            status VARCHAR(16) DEFAULT 'pending_approval',
            requested_by INTEGER NOT NULL,
            decided_by INTEGER,
            reason TEXT,
            decided_at TIMESTAMPTZ,
            review_result_id BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_skill_provenance (
            id BIGSERIAL PRIMARY KEY,
            skill_name VARCHAR(128) NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            source VARCHAR(64) DEFAULT '',
            detail JSONB,
            actor_id INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_skill_usage (
            id BIGSERIAL PRIMARY KEY,
            skill_name VARCHAR(128) NOT NULL,
            conversation_id BIGINT,
            owner_id INTEGER,
            success BOOLEAN DEFAULT TRUE,
            duration_ms DOUBLE PRECISION DEFAULT 0.0,
            error_detail TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
    ]
    indexes = [
        "CREATE INDEX IF NOT EXISTS ix_review_tasks_conv ON agent_review_tasks(conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_review_tasks_owner ON agent_review_tasks(owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_review_results_task ON agent_review_results(review_task_id)",
        "CREATE INDEX IF NOT EXISTS ix_review_results_owner ON agent_review_results(owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_skill_registry_name ON agent_skill_registry(name)",
        "CREATE INDEX IF NOT EXISTS ix_skill_approvals_name ON agent_skill_approvals(skill_name)",
        "CREATE INDEX IF NOT EXISTS ix_skill_provenance_name ON agent_skill_provenance(skill_name)",
        "CREATE INDEX IF NOT EXISTS ix_skill_usage_name ON agent_skill_usage(skill_name)",
    ]
    try:
        for sql in tables + indexes:
            await db.execute(text(sql))
        await db.commit()
        logger.info("Migration: ensured review + skill governance tables")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: review/governance tables check failed: %s", e)


async def ensure_checkpoint_table(db: AsyncSession) -> None:
    """Ensure agent_checkpoints table exists (idempotent)."""
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_checkpoints (
                id BIGSERIAL PRIMARY KEY,
                conversation_id BIGINT NOT NULL,
                checkpoint_id VARCHAR(64) NOT NULL,
                parent_checkpoint_id VARCHAR(64),
                step INTEGER DEFAULT 0,
                channel_values JSONB DEFAULT '{}'::jsonb,
                extra_meta JSONB DEFAULT '{}'::jsonb,
                owner_id INTEGER NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_checkpoint_pair
            ON agent_checkpoints (conversation_id, checkpoint_id)
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agent_checkpoints_conv ON agent_checkpoints(conversation_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agent_checkpoints_owner ON agent_checkpoints(owner_id)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_checkpoints table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: agent_checkpoints table check failed: %s", e)


async def ensure_understanding_tables(db: AsyncSession) -> None:
    """Ensure understanding loop tables exist (idempotent)."""
    tables = [
        """
        CREATE TABLE IF NOT EXISTS agent_understanding_packets (
            id BIGSERIAL PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            conversation_id BIGINT NOT NULL,
            trigger_reason VARCHAR(64) DEFAULT 'high_ambiguity',
            user_input TEXT DEFAULT '',
            intent TEXT DEFAULT '',
            concerns JSONB DEFAULT '[]'::jsonb,
            plan_critique TEXT DEFAULT '',
            retrieval_evidence JSONB DEFAULT '[]'::jsonb,
            summary TEXT DEFAULT '',
            rounds_used INTEGER DEFAULT 0,
            roles_executed JSONB DEFAULT '[]'::jsonb,
            resolved_profile_key VARCHAR(64) DEFAULT '',
            resolved_template VARCHAR(64) DEFAULT 'default',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_understanding_events (
            id BIGSERIAL PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            packet_id BIGINT NOT NULL,
            conversation_id BIGINT NOT NULL,
            role_name VARCHAR(64) NOT NULL,
            prompt TEXT DEFAULT '',
            response TEXT DEFAULT '',
            profile_key VARCHAR(64) DEFAULT '',
            round_index INTEGER DEFAULT 0,
            duration_ms DOUBLE PRECISION DEFAULT 0.0,
            success BOOLEAN DEFAULT TRUE,
            error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
    ]
    indexes = [
        "CREATE INDEX IF NOT EXISTS ix_understanding_packets_owner ON agent_understanding_packets(owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_understanding_packets_conv ON agent_understanding_packets(conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_understanding_events_owner ON agent_understanding_events(owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_understanding_events_packet ON agent_understanding_events(packet_id)",
    ]
    try:
        for sql in tables + indexes:
            await db.execute(text(sql))
        await db.commit()
        logger.info("Migration: ensured understanding loop tables")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: understanding tables check failed: %s", e)


async def ensure_memory_snapshot_table(db: AsyncSession) -> None:
    """Ensure agent_memory_snapshots table exists (idempotent)."""
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_memory_snapshots (
                id BIGSERIAL PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                conversation_id BIGINT,
                label VARCHAR(64) DEFAULT '',
                snapshot_type VARCHAR(32) DEFAULT 'conversation_start',
                token_estimate INTEGER DEFAULT 0,
                turn_count INTEGER DEFAULT 0,
                stable_rules_data JSONB,
                chunks_data JSONB,
                semantic_data JSONB,
                selection_audit JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_memory_snapshots_owner ON agent_memory_snapshots(owner_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_memory_snapshots_conv ON agent_memory_snapshots(conversation_id)"
        ))
        await db.commit()
        logger.info("Migration: ensured agent_memory_snapshots table")
    except Exception as e:
        await db.rollback()
        logger.warning("Migration: agent_memory_snapshots table check failed: %s", e)


_init_done: bool = False


async def run_init(db: AsyncSession) -> None:
    """Agent 模块启动初始化入口。在首次请求时执行一次，后续跳过（惰性初始化）。"""
    global _init_done
    if _init_done:
        return
    await ensure_migrated_tables(db)
    await ensure_timeline_column(db)
    await ensure_processing_column(db)
    await ensure_event_table(db)
    await ensure_snapshot_table(db)
    await ensure_agent_state_tables(db)
    await ensure_maintenance_state_table(db)
    await ensure_review_governance_tables(db)
    await ensure_memory_snapshot_table(db)
    await ensure_checkpoint_table(db)
    await ensure_understanding_tables(db)
    await ensure_default_prompts(db)
    await update_existing_prompts(db)
    _init_done = True
