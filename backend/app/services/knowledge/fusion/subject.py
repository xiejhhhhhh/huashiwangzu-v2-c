"""
L2 page-level fusion — three-stage subject discovery

1. Rule-based candidates (field prefixes, layout titles, dictionary hits)
2. LLM for complex cases (Pydantic constrained)
3. High-confidence subjects back to rule base
"""
from __future__ import annotations

import logging
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Enums ──

class SubjectType(str, Enum):
    brand = "品牌"
    product = "产品"
    ingredient = "成分"
    effect = "功效"
    testing = "检测"
    filing = "备案"
    membership = "会员方案"
    training = "培训"
    other = "其他"

# ── Pydantic schemas (LLM output constraint) ──

class SubjectCandidate(BaseModel):
    subject_type: SubjectType
    name: str = Field(..., description="主体名")
    reason: str = Field("", description="为什么是主体")
    evidence_pages: list[int] = Field(default_factory=lambda: [1])
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

class LLMSubjectOutput(BaseModel):
    subjects: list[SubjectCandidate] = Field(default_factory=list)
    should_ignore: list[str] = Field(default_factory=list)

# ── Rule-based trigger patterns ──

_TRIGGER_PATTERNS: dict[SubjectType, list[str]] = {
    SubjectType.testing: ["检测机构", "报告编号", "检验结论", "检测日期", "检验项目", "检测报告"],
    SubjectType.filing: ["备案号", "备案人", "生产企业", "执行标准", "备案编号"],
    SubjectType.product: ["产品名称", "规格", "产品说明", "套盒名称", "系列", "净含量"],
    SubjectType.ingredient: ["成分", "INCI", "全成分"],
    SubjectType.effect: ["功效", "保湿", "美白", "修护", "抗皱", "舒缓", "控油"],
    SubjectType.membership: ["会员", "会员价", "转介绍", "折扣", "赠品", "权益", "方案"],
    SubjectType.training: ["培训", "制度", "流程", "岗位", "考核", "话术"],
    SubjectType.brand: ["品牌", "母品牌", "子品牌"],
}

_SEED_BRANDS = {"华世王镞", "俏小喵", "娇薇诗", "清颜", "轻颜", "博泉"}


def _rule_based_candidates(text: str, layout_data: dict | None = None) -> list[dict]:
    candidates: list[dict] = []
    found_types: set[SubjectType] = set()

    for stype, patterns in _TRIGGER_PATTERNS.items():
        for p in patterns:
            if p in text:
                found_types.add(stype)
                break

    for brand in _SEED_BRANDS:
        if brand in text:
            candidates.append({
                "subject_type": SubjectType.brand.value,
                "name": brand,
                "reason": f"种子品牌词典命中: {brand}",
                "evidence_pages": [1],
                "confidence": 0.85,
                "source": "rule",
            })

    for stype in found_types:
        candidate_name = f"{stype.value}信息"
        already = any(c["name"] == candidate_name for c in candidates)
        if not already:
            candidates.append({
                "subject_type": stype.value,
                "name": candidate_name,
                "reason": f"字段前缀/关键词触发: {stype.value}",
                "evidence_pages": [1],
                "confidence": 0.7,
                "source": "rule",
            })

    return candidates


def _llm_discover_subjects(
    text: str,
    existing_candidates: list[dict],
) -> list[dict]:
    # Placeholder: in production, call the controlled LLM service.
    # For now, return empty to indicate rule-only mode.
    return []


def discover_subjects(
    fusion_text: str,
    sources: list[dict],
    use_llm: bool = False,
) -> list[dict]:
    if not fusion_text or not fusion_text.strip():
        return []

    candidates = _rule_based_candidates(fusion_text, None)

    if use_llm:
        llm_candidates = _llm_discover_subjects(fusion_text, candidates)
        candidates.extend(llm_candidates)

    seen_names: set[str] = set()
    deduped: list[dict] = []
    for c in candidates:
        name = c.get("name", "")
        if name not in seen_names:
            seen_names.add(name)
            deduped.append(c)

    return deduped
