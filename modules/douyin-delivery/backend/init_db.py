"""Initialize DB tables and default prompts for douyin-delivery module."""

import logging

from app.database import engine
from app.models.base import Base
from sqlalchemy import text as sa_text

logger = logging.getLogger("v2.douyin_delivery").getChild("init_db")

from .models import (
    DouyinAccount,
    DouyinAdCopy,
    DouyinCampaign,
    DouyinDeliveryTask,
    DouyinMaterial,
    DouyinProduct,
    DouyinPrompt,
    DouyinScript,
)

DOUYIN_TABLES = [
    "douyin_products",
    "douyin_scripts",
    "douyin_ad_copies",
    "douyin_campaigns",
    "douyin_accounts",
    "douyin_materials",
    "douyin_delivery_tasks",
    "douyin_prompts",
]
DOUYIN_MODEL_CLASSES = (
    DouyinProduct,
    DouyinScript,
    DouyinAdCopy,
    DouyinCampaign,
    DouyinAccount,
    DouyinMaterial,
    DouyinDeliveryTask,
    DouyinPrompt,
)

CHANNEL_LABELS = {
    "local_push": "本地推",
    "ocean_engine": "巨量引擎",
    "qianchuan": "千川",
}

DEFAULT_PROMPTS = [
    {
        "key": "persona_system",
        "name": "人设/调性系统提示词",
        "category": "system",
        "channel": "",
        "content": (
            "你是一个专业的问题肌修护专家，代表俏小喵品牌。\n\n"
            "人设要求：\n"
            "- 专业但不高冷：用通俗易懂的语言解释专业问题\n"
            "- 亲和力：像朋友一样聊天，不摆架子\n"
            "- 权威感：用成分科学和临床数据支撑观点\n"
            "- 品牌调性：俏小喵——专注问题肌修护，科学有效、温和亲肤\n\n"
            "抖音口语化要求（和公众号不同！）：\n"
            "- 开头3秒抓眼球：用强烈痛点或反差开场\n"
            "- 短句 + 语气词 + 停顿：适合口播，不是读文章\n"
            "- 多用设问：「你是不是也这样？」「知道为什么吗？」\n"
            "- 不要学术感，要像闺蜜聊天的感觉\n"
            "- 信息密度高，但每句话一听就懂\n"
            "- 结尾强引导：关注/评论区/橱窗/直播间"
        ),
        "description": "定义AI投放助手的抖音人设、调性和口播风格",
    },
    {
        "key": "script_generation",
        "name": "口播脚本生成提示词",
        "category": "script",
        "channel": "",
        "content": (
            "你正在为俏小喵品牌生成一条抖音短视频的口播脚本。\n\n"
            "产品/卖点：{product}\n"
            "投放渠道：{channel}（{channel_label}）\n\n"
            "请生成以下结构的内容：\n\n"
            "## 开头钩子（前3秒）\n"
            "一个强烈的问题/反差/数据/场景，立刻抓住注意力。\n\n"
            "## 痛点共鸣（3-15秒）\n"
            "描述目标用户的真实困扰，让观众觉得「说的就是我」。\n\n"
            "## 卖点展开（15-40秒）\n"
            "介绍产品核心卖点，用成分和功效说话，口语化表达。\n"
            "涉及成分/功效的地方标注【知识库校验】。\n\n"
            "## 信任背书（40-50秒）\n"
            "成分科学依据、品牌理念、用户口碑等。\n\n"
            "## 行动引导（最后10秒）\n"
            "明确的下一步动作：关注/评论区提问/点击橱窗/去直播间。\n\n"
            "## 拍摄建议\n"
            "简单说明画面/表情/语气的建议。\n\n"
            "## 标题候选项（3个）\n"
            "抓眼球、带关键词的标题。\n\n"
            "## 话题标签（5-8个）\n"
            "相关热门话题标签。"
        ),
        "description": "根据产品/卖点生成抖音口播脚本完整结构",
    },
    {
        "key": "ad_copy_generation",
        "name": "广告文案生成提示词",
        "category": "ad_copy",
        "channel": "",
        "content": (
            "你正在为俏小喵品牌生成抖音投放广告文案。\n\n"
            "产品/卖点：{product}\n"
            "投放渠道：{channel}（{channel_label}）\n"
            "广告类型：{ad_type}\n\n"
            "请生成以下内容：\n\n"
            "## 短标题（25字以内）\n"
            "吸引眼球的核心标题，带关键词。\n\n"
            "## 广告描述（100字以内）\n"
            "简洁有力地说清楚产品价值和行动理由。\n\n"
            "## 行动号召按钮文案\n"
            "如「立即购买」「了解更多」「免费领取」等。\n\n"
            "## 定向人群建议\n"
            "描述目标人群画像（性别/年龄/兴趣/痛点）。\n\n"
            "## 落地页建议\n"
            "建议跳转的页面类型和内容要点。\n\n"
            "渠道说明：\n"
            "- 本地推：侧重周边门店引流，强调线下体验\n"
            "- 巨量引擎：侧重精准投放，用数据和效果说话\n"
            "- 千川：侧重直播/短视频带货，强调限时优惠和转化"
        ),
        "description": "根据产品和渠道生成广告投放文案",
    },
    {
        "key": "channel_local_push",
        "name": "本地推-渠道说明",
        "category": "channel_info",
        "channel": "local_push",
        "content": (
            "本地推是抖音针对本地生活/门店的投放工具。\n"
            "特点：\n"
            "- 侧重周边3-5公里的人群覆盖\n"
            "- 适合有实体门店的品牌\n"
            "- 文案强调「附近」「到店体验」「限时到店」\n"
            "- 转化目标：到店核销/电话咨询"
        ),
        "description": "本地推渠道特点和文案风格说明",
    },
    {
        "key": "channel_ocean_engine",
        "name": "巨量引擎-渠道说明",
        "category": "channel_info",
        "channel": "ocean_engine",
        "content": (
            "巨量引擎是抖音的综合广告投放平台。\n"
            "特点：\n"
            "- 支持多种广告形式（信息流/搜索/开屏）\n"
            "- 精准人群定向（兴趣/行为/人群包）\n"
            "- 文案强调数据化效果和成分功效\n"
            "- 转化目标：商品购买/表单留资/App下载"
        ),
        "description": "巨量引擎渠道特点和文案风格说明",
    },
    {
        "key": "channel_qianchuan",
        "name": "千川-渠道说明",
        "category": "channel_info",
        "channel": "qianchuan",
        "content": (
            "千川是抖音电商的广告投放平台。\n"
            "特点：\n"
            "- 侧重直播带货和短视频带货\n"
            "- 强调限时优惠、秒杀、赠品\n"
            "- 文案要制造紧迫感和稀缺性\n"
            "- 转化目标：直播间进入/商品点击/直接购买"
        ),
        "description": "千川渠道特点和文案风格说明",
    },
    {
        "key": "ingredient_validation",
        "name": "成分功效校验提示词",
        "category": "validation",
        "channel": "",
        "content": (
            "你是一个成分科学审核专家。请校验以下抖音投放内容中涉及的\n"
            "成分名称、功效声称、作用机理是否科学准确：\n\n"
            "{content}\n\n"
            "请逐条检查并返回：\n"
            "1. ✅ 准确的内容\n"
            "2. ⚠️ 需要修正的内容（指出问题 + 建议修改）\n"
            "3. ❌ 错误的内容（指出错误 + 正确参考）\n"
            "4. 建议补充的知识点\n\n"
            "注意抖音投放场景下：不要过度夸大功效，符合广告法要求。"
        ),
        "description": "校验投放内容中的成分/功效是否科学准确",
    },
]


def _init_db():
    """Create tables and seed default prompts if needed."""
    try:
        douyin_tables = [t for n, t in Base.metadata.tables.items() if n.startswith("douyin_")]
        import asyncio
        async def _create():
            async with engine.begin() as conn:
                await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=douyin_tables))
        asyncio.run(_create())
        logger.info("Tables created/verified: %s", ", ".join(DOUYIN_TABLES))
    except Exception as exc:
        logger.warning("Table creation skipped (may already exist): %s", exc)

    try:
        import asyncio

        from app.database import AsyncSessionLocal

        async def _seed_prompts():
            async with AsyncSessionLocal() as db:
                for dp in DEFAULT_PROMPTS:
                    r = await db.execute(
                        sa_text(
                            "SELECT id FROM douyin_prompts WHERE key = :key AND owner_id = 0 AND deleted = false LIMIT 1"
                        ),
                        {"key": dp["key"]},
                    )
                    if r.scalar_one_or_none():
                        continue
                    prompt = DouyinPrompt(
                        owner_id=0,
                        key=dp["key"],
                        name=dp["name"],
                        content=dp["content"],
                        description=dp.get("description", ""),
                        category=dp["category"],
                        channel=dp.get("channel", ""),
                    )
                    db.add(prompt)
                await db.commit()
                logger.info("Default prompts seeded")

        asyncio.run(_seed_prompts())
    except Exception as exc:
        logger.warning("Prompt seeding skipped: %s", exc)


_run_startup_init = _init_db
