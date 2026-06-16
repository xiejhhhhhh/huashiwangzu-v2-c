"""L2: Auto-pass candidates hitting brand/product/ingredient/efficacy whitelist
with multi-source corroboration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge.candidate import ExtractCandidate
from app.services.knowledge.dictionary.seed import (
    is_brand, resolve_brand, is_transition_concept,
    is_known_entity,
)
from app.services.knowledge.dictionary.quality import (
    passes_entity_gate, is_detection_conclusion,
    should_be_attribute, is_entity_quality_adjudged,
)
from app.services.knowledge.candidate.llm_client import fetch_known_entity_names


async def run_l2_pass(db: AsyncSession, batch_size: int = 500) -> dict:
    result = await db.execute(
        select(ExtractCandidate).where(
            ExtractCandidate.verdict_status == 0
        ).limit(batch_size)
    )
    candidates = list(result.scalars().all())
    known = await fetch_known_entity_names(db)

    stats = {"passed": 0, "attribute": 0, "ignored": 0}

    for c in candidates:
        content = c.content.strip()

        # Detection conclusion → attribute/evidence, not entity
        if is_detection_conclusion(content):
            c.verdict_status = 3
            c.extra = c.extra or {}
            c.extra["l2_reason"] = "detection conclusion → attribute/evidence"
            stats["ignored"] += 1
            continue

        if should_be_attribute(content):
            c.verdict_status = 3
            c.extra = c.extra or {}
            c.extra["l2_reason"] = "attribute-like → attribute pool"
            stats["attribute"] += 1
            continue

        if not passes_entity_gate(content):
            c.verdict_status = 2
            c.extra = c.extra or {}
            c.extra["l2_reason"] = "failed quality gate"
            stats["ignored"] += 1
            continue

        if is_brand(content) or is_transition_concept(content) or is_known_entity(content, known):
            multi_source = _has_multi_source(c)
            if multi_source or c.confidence >= 0.7:
                c.verdict_status = 1
                c.extra = c.extra or {}
                c.extra["l2_reason"] = "auto-pass: whitelist match"
                c.extra["entity_type"] = _infer_entity_type(content)
                stats["passed"] += 1
                continue

    await db.flush()
    return stats


def _has_multi_source(candidate: ExtractCandidate) -> bool:
    if candidate.extra:
        sources = candidate.extra.get("sources", [])
        if isinstance(sources, list) and len(set(sources)) >= 2:
            return True
    return False


def _infer_entity_type(content: str) -> str:
    if is_brand(content):
        return "brand"
    if is_transition_concept(content):
        return "member_plan"
    return "product"
