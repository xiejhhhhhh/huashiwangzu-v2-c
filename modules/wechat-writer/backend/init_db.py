"""Initialize DB tables and default prompts for wechat-writer module."""

import asyncio
import logging

from app.database import AsyncSessionLocal, engine
from app.models.base import Base
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.wechat_writer").getChild("init_db")

# 确保 models 被 import 从而注册到 Base.metadata
from .models import WechatDraft, WechatPrompt  # noqa: F401, E402

WECHAT_TABLES = ["wechat_drafts", "wechat_prompts"]

DEFAULT_PROMPTS = [
    {
        "key": "persona_system",
        "name": "人设/调性系统提示词",
        "category": "system",
        "content": (
            "你是一个专业的问题肌修护专家，代表俏小喵品牌。\n\n"
            "人设要求：\n"
            "- 专业但不高冷：用通俗易懂的语言解释专业问题\n"
            "- 亲和力：像朋友一样聊天，不摆架子\n"
            "- 权威感：用成分科学和临床数据支撑观点\n"
            "- 品牌调性：俏小喵——专注问题肌修护，科学有效、温和亲肤\n\n"
            "写作风格：\n"
            "- 段落简短，多用问句引发共鸣\n"
            "- 避免过度营销感，先给价值再提产品\n"
            "- 用「你」来对话读者，拉近距离\n"
            "- 重要观点用加粗强调\n"
            "- 每篇文章结尾有行动引导（关注/咨询/试用）"
        ),
        "description": "定义AI写作助手的人设、调性和写作风格",
    },
    {
        "key": "topic_generation",
        "name": "选题生成提示词",
        "category": "topic",
        "content": (
            "你是俏小喵品牌的问题肌修护专家，正在为公众号「华世王镞问题肌修护专家」策划选题。\n\n"
            "品牌背景：俏小喵是一个专注问题肌修护的国货品牌，主打科学有效、温和亲肤的护肤方案。\n"
            "目标读者：有敏感肌、痘痘肌、红血丝、屏障受损等肌肤问题困扰的年轻女性（22-35岁）。\n"
            "公众号调性：专业但不高冷、亲和有温度、科学护肤。\n\n"
            "根据以下创作方向，生成5个选题建议：\n"
            "{direction}\n\n"
            "要求：\n"
            "1. 选题要切中目标读者的真实痛点\n"
            "2. 结合当前季节和热门护肤话题\n"
            "3. 每个选题给出1-2句推荐理由\n"
            "4. 标注是否涉及成分/功效知识校验\n"
            "5. 格式：标题 + 一句话简介 + 推荐理由 + 涉及成分"
        ),
        "description": "根据产品或方向生成公众号选题建议",
    },
    {
        "key": "outline_generation",
        "name": "大纲生成提示词",
        "category": "outline",
        "content": (
            "你是俏小喵品牌的问题肌修护专家，正在为公众号文章撰写大纲。\n\n"
            "选题：{topic}\n"
            "创作方向：{direction}\n\n"
            "请生成一个详细的文章大纲，要求：\n"
            "1. 开头：吸引注意力的问题/场景/数据引入\n"
            "2. 正文：3-5个核心段落，每个段落包含：\n"
            "   - 段落主题\n"
            "   - 核心观点\n"
            "   - 涉及的成分/功效（标注是否需要知识库校验）\n"
            "3. 结尾：总结 + 品牌植入（自然不硬广） + 互动引导\n"
            "4. 标题候选项：3个备选标题\n\n"
            "输出格式为章节结构即可，每个段落100字以内的要点说明。"
        ),
        "description": "根据选题生成公众号文章大纲",
    },
    {
        "key": "article_generation",
        "name": "成文生成提示词",
        "category": "article",
        "content": (
            "你正在为俏小喵品牌公众号「华世王镞问题肌修护专家」撰写一篇专业文章。\n\n"
            "选题：{topic}\n"
            "大纲：\n{outline}\n\n"
            "写作要求：\n"
            "1. 遵循人设：专业的问题肌修护专家，亲和但不失权威\n"
            "2. 段落控制在200字以内，多用短句\n"
            "3. 专业成分名称用加粗标记（如**神经酰胺**、**积雪草苷**）\n"
            "4. 每段围绕一个核心观点展开\n"
            "5. 适当使用设问句：「你有没有过这样的经历？」「知道为什么吗？」\n"
            "6. 结尾自然融入俏小喵品牌理念，不要硬广\n"
            "7. 全文1500-2500字，适合公众号阅读\n"
            "8. 重要知识点标注【知识库校验】，提示后期需要专业知识核对\n\n"
            "请严格按照大纲结构撰写完整的文章初稿。"
        ),
        "description": "根据大纲生成完整的公众号文章初稿",
    },
    {
        "key": "ingredient_validation",
        "name": "成分功效校验提示词",
        "category": "validation",
        "content": (
            "你是一个成分科学审核专家。请校验以下护肤相关内容中涉及的\n"
            "成分名称、功效声称、作用机理是否科学准确：\n\n"
            "{content}\n\n"
            "请逐条检查并返回：\n"
            "1. ✅ 准确的内容\n"
            "2. ⚠️ 需要修正的内容（指出问题 + 建议修改）\n"
            "3. ❌ 错误的内容（指出错误 + 正确参考）\n"
            "4. 建议补充的知识点"
        ),
        "description": "校验文章中的成分/功效内容是否科学准确",
    },
]


async def ensure_wechat_tables() -> None:
    """Create this module's tables using SQLAlchemy async engine."""
    wechat_tables = [table for name, table in Base.metadata.tables.items() if name.startswith("wechat_")]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=wechat_tables))
    logger.info("Ensured %d wechat_* tables exist: %s", len(wechat_tables), ", ".join(WECHAT_TABLES))


async def seed_default_prompts(db: AsyncSession) -> int:
    """Insert default prompts once. Existing active global prompts are preserved."""
    seeded = 0
    for prompt_data in DEFAULT_PROMPTS:
        result = await db.execute(
            sa_text(
                "SELECT id FROM wechat_prompts "
                "WHERE key = :key AND owner_id = 0 AND deleted = false LIMIT 1"
            ),
            {"key": prompt_data["key"]},
        )
        if result.scalar_one_or_none():
            continue
        db.add(
            WechatPrompt(
                owner_id=0,
                key=prompt_data["key"],
                name=prompt_data["name"],
                content=prompt_data["content"],
                description=prompt_data.get("description", ""),
                category=prompt_data["category"],
            )
        )
        seeded += 1
    await db.commit()
    logger.info("Ensured default wechat prompts (seeded=%d)", seeded)
    return seeded


async def run_init(db: AsyncSession | None = None) -> None:
    """Startup initialization entrypoint for tests, sandbox, and router import."""
    await ensure_wechat_tables()
    if db is not None:
        await seed_default_prompts(db)
        return
    async with AsyncSessionLocal() as session:
        await seed_default_prompts(session)


def _run_startup_init() -> asyncio.Task[None] | None:
    """Run module startup init safely whether an event loop is already running."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        task = loop.create_task(run_init())

        def _log_task_result(done_task: asyncio.Task[None]) -> None:
            try:
                done_task.result()
            except Exception as exc:
                logger.warning("Wechat-writer startup init failed: %s", exc)

        task.add_done_callback(_log_task_result)
        logger.info("Scheduled wechat-writer startup init on running event loop")
        return task

    try:
        asyncio.run(run_init())
        logger.info("Wechat-writer startup init complete")
    except Exception as exc:
        logger.warning("Wechat-writer startup init failed: %s", exc)
    return None
