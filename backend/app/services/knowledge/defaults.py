"""Seed dictionary configuration for knowledge base entity governance.

Built-in brands, entity types, transition concept whitelist,
organization suffixes, and document types.
"""

# ── Brand hierarchy (母品牌 + 子品牌) ──
BRANDS: dict[str, dict] = {
    "华世王镞": {"type": "brand", "sub_brands": ["俏小喵", "娇薇诗", "清颜", "轻颜", "博泉"]},
    "俏小喵": {"type": "brand", "parent": "华世王镞"},
    "娇薇诗": {"type": "brand", "parent": "华世王镞"},
    "清颜": {"type": "brand", "parent": "华世王镞"},
    "轻颜": {"type": "brand", "parent": "华世王镞", "aliases": ["清颜"]},
    "博泉": {"type": "brand", "parent": "华世王镞"},
}

# 别名关系：标准名 → 别名列表
BRAND_ALIASES: dict[str, list[str]] = {
    "清颜": ["轻颜", "qingyan", "QingYan"],
    "轻颜": ["清颜", "qingyan", "QingYan"],
    "华世王镞": ["HSWZ", "华世王族", "华世王钅"],
    "俏小喵": ["俏小猫", "qiaoxiaomiao"],
    "娇薇诗": ["jiaoweishi", "JWS"],
    "博泉": ["boquan", "BoQuan"],
}

# ── Allowed entity types (aligned with LLM_ALLOWED_TYPES) ──
ENTITY_TYPES: list[str] = [
    "brand",           # 品牌(母/子)
    "product",         # 产品
    "kit",             # 套盒
    "ingredient",      # 成分
    "efficacy",        # 功效
    "organization",    # 组织/检测机构
    "doc_type",        # 资料类型(仅作筛选标签)
    "member_plan",     # 会员方案
    "training_system", # 培训制度
]

# ── Transition concept whitelist ──
# Words that look generic but have specific business meaning
TRANSITION_CONCEPT_WHITELIST: set[str] = {
    "终端客户会员方案", "转介绍奖励", "拿货折上折",
    "标准流程", "擦霜流程", "培训流程", "招商政策",
}

# ── Organization suffixes (detect org names) ──
ORG_SUFFIXES: list[str] = [
    "有限公司", "有限责任公司", "检测技术", "研究所", "研究院",
    "集团", "股份", "工作室", "商行", "厂",
]

# ── Document types (not entity, just filter tags) ──
DOC_TYPES: list[str] = [
    "产品手册", "检测报告", "会员方案", "培训资料",
    "招商手册", "品牌手册", "产品画册", "宣传单页",
]

# ── Generic / stop words (should never become an entity) ──
STOP_WORDS: set[str] = {
    "产品", "报告", "文档", "图片", "公司", "客户", "方案",
    "手册", "资料", "画册", "页面", "文件", "来源",
}

# ── Process / backend words that should be auto-ignored ──
PROCESS_WORDS: set[str] = {
    "OCR文字", "视觉理解", "交叉印证", "页面原文融合",
    "脚本文字", "页面资源", "布局数据", "截图路径",
    "pdf", "PDF", "页面摘要", "来源类型",
}

# ── Entity types allowed for LLM output ──
LLM_ALLOWED_TYPES: list[str] = [
    "brand", "product", "kit", "ingredient", "efficacy",
    "organization", "doc_type", "member_plan", "training_system",
]

# ── Types forbidden from auto-promoting to dictionary ──
LLM_BLOCKED_TYPES: set[str] = {"concept", "other", "unknown"}
