"""
L7 标签准入规则 (Admission Gate)
标签只收高价值短词:
  准入: 品牌/产品名/成分/功效短词/资料类型/业务方案短语
  拒绝: 后端过程名(OCR/视觉理解)/路径JSON/纯编号/机构长名/泛词(产品/报告/方案)/长句

通过准入的标签写 knowledge_labels(passed_admission=true)
"""
import logging
import re

logger = logging.getLogger(__name__)

# ── 准入通行: 返回 (True, category) ──

ADMITTED_CATEGORIES = {
    "brand", "product", "ingredient", "effect",
    "material_type", "business_plan",
}

KNOWN_BRANDS = [
    "华世王镞", "俏小喵", "娇薇诗", "清颜", "轻颜", "博泉",
]

MATERIAL_TYPES = [
    "产品手册", "检测报告", "会员方案", "培训资料",
    "备案资料", "功效报告", "质检报告", "产品介绍",
    "使用说明", "宣传资料", "技术资料",
]

# ── 拒绝模式 ──

REJECT_BACKEND_PROCESS = re.compile(
    r"^(OCR文字|视觉理解|交叉印证|页面原文融合|脚本文本|页面资源"
    r"|截图|缩略图|缓存|页图说明|视觉分析"
    r"|知识_|knowledge_|extract_|fusion_|page_source)",
    re.IGNORECASE,
)

REJECT_PATH_JSON = re.compile(r"^([a-zA-Z]:)?[/\\]|^\{.*\}\s*$|^\[.*\]\s*$")

REJECT_PURE_NUMBER = re.compile(r"^\d+$")

REJECT_LONG_ORG = re.compile(r"^(广东|广州|深圳|上海|北京)?[^，。]{5,}(有限公[司]|研究院|实验室|检测中心|机构|委员会)$")
REJECT_ORG_SUFFIX = re.compile(r".{2,}(中心|实验室|研究院|有限公[司]|委员会|部门|小组|团队)$")

REJECT_GENERIC = re.compile(r"^(产品|报告|方案|文档|图片|公司|客户|资料|文件|数据|信息|内容|项目|系统|服务|平台|管理|测试|实验|研发|开发|设计|运营|推广|活动|通知|公告|规定|制度|流程)$")

REJECT_LONG_SENTENCE = re.compile(r"^.{20,}$")

# 功效词白名单
EFFECT_KEYWORDS = [
    "保湿", "美白", "修护", "抗皱", "舒缓", "控油",
    "祛痘", "淡斑", "紧致", "补水", "滋养", "防晒",
    "隔离", "提亮", "抗氧化", "抗衰老", "收缩毛孔",
    "去角质", "深层清洁", "镇定", "抗敏", "祛黄",
]


class AdmissionGate:

    @staticmethod
    def check(label: str, category_hint: str | None = None) -> tuple[bool, str]:
        """检查标签是否通过准入, 返回 (passed, reason)"""
        text = label.strip()
        if not text:
            return False, "empty"

        # ── 拒绝检查 ──
        if REJECT_BACKEND_PROCESS.match(text):
            return False, f"rejected: backend process name: {text}"

        if REJECT_PATH_JSON.match(text):
            return False, f"rejected: path or JSON-like: {text}"

        if REJECT_PURE_NUMBER.match(text):
            return False, f"rejected: pure number: {text}"

        if REJECT_LONG_ORG.match(text):
            return False, f"rejected: long org name: {text}"
        if REJECT_ORG_SUFFIX.match(text) and text not in KNOWN_BRANDS:
            return False, f"rejected: org suffix pattern: {text}"

        if REJECT_GENERIC.match(text):
            return False, f"rejected: generic word: {text}"

        if REJECT_LONG_SENTENCE.match(text):
            return False, f"rejected: long sentence (>20 chars): {text}"

        # ── 准入检查 ──
        if text in KNOWN_BRANDS:
            return True, "admitted: known brand"

        if text in MATERIAL_TYPES:
            return True, "admitted: material type"

        if category_hint in ADMITTED_CATEGORIES:
            return True, f"admitted: category={category_hint}"

        if text in EFFECT_KEYWORDS:
            return True, "admitted: effect keyword"

        if (
            len(text) <= 8
            and re.search(r"[\u4e00-\u9fff]", text)
            and not re.match(r"^[\d\W]+$", text)
            and text not in (
                "产品", "报告", "方案", "文档", "公司", "数据", "信息",
                "内容", "项目", "系统", "服务", "平台", "管理",
                "图片", "客户", "资料", "文件", "第1页", "首页",
                "测试", "实验", "研发", "开发", "设计", "运营", "推广",
                "活动", "通知", "公告", "规定", "制度", "流程", "说明",
            )
        ):
            return True, "admitted: short high-value term"

        return False, f"rejected: does not meet admission criteria: {text}"

    @staticmethod
    def batch_check(labels: list[dict]) -> list[dict]:
        """批量检查标签候选. 每个 dict: {label, category_hint?}"""
        results = []
        for item in labels:
            label = item.get("label", "")
            hint = item.get("category_hint")
            passed, reason = AdmissionGate.check(label, hint)
            results.append({
                "label": label,
                "passed": passed,
                "reason": reason,
            })
        return results
