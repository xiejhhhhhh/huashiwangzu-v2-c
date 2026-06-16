"""L3: LLM batch judgment for candidates that rules cannot decide.

Uses Pydantic-constrained output to ensure LLM stays within allowed types.
New entities only enter candidates, never the dictionary directly.
"""

import logging
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge.candidate import ExtractCandidate
from typing import Optional
from app.services.knowledge.candidate.llm_client import (
    fetch_known_entity_names, build_llm_prompt, call_llm,
    service_layer_new_check, content_matches,
)

logger = logging.getLogger(__name__)


async def run_l3_llm(
    db: AsyncSession,
    batch_size: int = 50,
    model_id: str = "gemma-4",
) -> dict[str, Any]:
    result = await db.execute(
        select(ExtractCandidate).where(
            ExtractCandidate.verdict_status == 0
        ).order_by(ExtractCandidate.confidence.desc()).limit(batch_size)
    )
    batch = list(result.scalars().all())
    if not batch:
        return {"processed": 0, "passed": 0, "ignored": 0, "attribute": 0}

    known_names = await fetch_known_entity_names(db)
    prompt = build_llm_prompt(batch, known_names)
    llm_result = await call_llm(prompt, model_id=model_id)

    stats = {"processed": 0, "passed": 0, "ignored": 0, "attribute": 0}
    candidate_map = {c.id: c for c in batch}

    def _pop_candidate(key: str) -> Optional[ExtractCandidate]:
        for cid, cand in list(candidate_map.items()):
            if cand.content.strip() == key or content_matches(cand.content, key):
                del candidate_map[cid]
                return cand
        return None

    for ent in llm_result.entities:
        ent = service_layer_new_check(ent, known_names)
        cand = _pop_candidate(ent.standard_name)
        if cand is None:
            continue
        cand.extra = cand.extra or {}
        cand.extra["l3_entity_type"] = ent.entity_type
        cand.extra["l3_confidence"] = ent.confidence
        cand.extra["l3_reason"] = ent.reason
        if ent.is_new:
            cand.extra["l3_is_new"] = True
            cand.extra["l3_action"] = "stay_candidate"
        else:
            cand.verdict_status = 1
            cand.extra["l3_action"] = "confirmed"
            stats["passed"] += 1
        stats["processed"] += 1

    for attr in llm_result.attributes:
        cand = _pop_candidate(attr.attr_value)
        if cand is None:
            continue
        cand.verdict_status = 3
        cand.extra = cand.extra or {}
        cand.extra["l3_action"] = "attribute"
        cand.extra["l3_attribute_subject"] = attr.subject
        cand.extra["l3_attribute_name"] = attr.attr_name
        stats["attribute"] += 1
        stats["processed"] += 1

    for ignore_term in llm_result.to_ignore:
        cand = _pop_candidate(ignore_term)
        if cand is None:
            continue
        cand.verdict_status = 2
        cand.extra = cand.extra or {}
        cand.extra["l3_action"] = "ignored"
        cand.extra["l3_reason"] = "LLM classified as ignorable"
        stats["ignored"] += 1
        stats["processed"] += 1

    await db.flush()
    return stats
