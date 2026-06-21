"""Agent 模块表初始化：确保三层提示词默认数据存在，并执行无痛迁移。"""
import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from models import AgentSystemPrompt, AgentEnterprisePrompt, AgentUserProfile

logger = logging.getLogger("v2.agent.init_db")

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


async def run_init(db: AsyncSession) -> None:
    """Agent 模块启动初始化入口。"""
    await ensure_timeline_column(db)
    await ensure_default_prompts(db)
    await update_existing_prompts(db)
