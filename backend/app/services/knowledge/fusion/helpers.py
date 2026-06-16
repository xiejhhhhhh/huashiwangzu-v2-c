from __future__ import annotations

import re

from app.services.knowledge.fusion.conflict import ConflictEntry


def summarize_text(text: str, max_len: int = 300) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_period = truncated.rfind("。")
    if last_period > max_len // 2:
        return truncated[:last_period] + "。"
    return truncated + "…"


def estimate_quality(
    fusion_text: str,
    conflicts: list[ConflictEntry],
    subject_candidates: list[dict],
) -> float:
    score = 1.0
    if not fusion_text or len(fusion_text.strip()) < 20:
        score -= 0.3
    if fusion_text and len(fusion_text.strip()) < 100:
        score -= 0.1
    n_severe = sum(1 for conflict in conflicts if conflict.severity in ("error", "warning"))
    score -= n_severe * 0.15
    score += min(len(subject_candidates) * 0.05, 0.15)
    return max(0.0, min(1.0, score))


def sources_to_evidence(sources: list[dict]) -> dict:
    evidence_map: dict[str, list[dict]] = {}
    for source in sources:
        source_type = source.get("source_type", "unknown")
        evidence_map.setdefault(source_type, [])
        evidence_map[source_type].append({
            "page_num": source.get("page_num", 1),
            "source_id": source.get("id"),
            "screenshot_md5": source.get("screenshot_md5"),
        })
    return evidence_map


def extract_attributes(text: str, subjects: list[dict]) -> list[dict]:
    attributes: list[dict] = []
    if not text:
        return attributes

    attr_rules = [
        (r"检测机构[：:]\s*(.+?)(?:[\n，；,]|$)", "检测机构"),
        (r"报告编号[：:]\s*(.+?)(?:[\n，；,]|$)", "报告编号"),
        (r"备案号[：:]\s*(.+?)(?:[\n，；,]|$)", "备案号"),
        (r"产品名称[：:]\s*(.+?)(?:[\n，；,]|$)", "产品名称"),
        (r"规格[：:]\s*(.+?)(?:[\n，；,]|$)", "规格"),
        (r"净含量[：:]\s*(.+?)(?:[\n，；,]|$)", "净含量"),
        (r"会员价[：:]\s*(.+?)(?:[\n，；,]|$)", "会员价"),
        (r"执行标准[：:]\s*(.+?)(?:[\n，；,]|$)", "执行标准"),
        (r"生产企业[：:]\s*(.+?)(?:[\n，；,]|$)", "生产企业"),
        (r"备案人[：:]\s*(.+?)(?:[\n，；,]|$)", "备案人"),
        (r"检验结论[：:]\s*(.+?)(?:[\n，；,]|$)", "检验结论"),
    ]

    for pattern, attr_name in attr_rules:
        match = re.search(pattern, text)
        if not match:
            continue
        value = match.group(1).strip()
        if not value:
            continue
        subject = ""
        for subject_item in subjects:
            if subject_item.get("subject_type") in ("检测", "备案", "产品", "会员方案"):
                subject = subject_item["name"]
                break
        attributes.append({
            "subject": subject,
            "attr_name": attr_name,
            "attr_value": value,
            "source": "rule",
        })
    return attributes
