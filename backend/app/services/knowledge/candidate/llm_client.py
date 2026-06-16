"""Shared LLM prompt building and client for L3 candidate judgment."""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge.entity import Entity
from app.models.knowledge.candidate import ExtractCandidate
from app.schemas.knowledge_ext import LlmBatchResult, LlmEntityOutput
from app.services.knowledge.dictionary.seed import (
    get_llm_allowed_types, is_llm_type_blocked, is_known_entity,
)

logger = logging.getLogger(__name__)

LLM_JUDGE_PROMPT = """You are a knowledge base entity classifier. Your task is to classify each candidate term.

Allowed entity types: {allowed_types}
Blocked from auto-promotion: {blocked_types}

Known entities in dictionary (you MUST choose from these if possible):
{known_entities}

Rules:
1. If a term matches a known entity, use its standard name.
2. If a term is clearly a new entity, set entity_type to one of the allowed types and mark is_new=true.
3. If a term is garbage/generic/unclassifiable, put it in to_ignore.
4. If a term looks like an attribute (field=value or detection conclusion), put it in attributes.
5. NEVER output entity_type "concept" or "other" — those are forbidden.
6. Be conservative: if unsure, put in to_ignore rather than guessing.

Return as strict JSON matching the schema.
"""


async def fetch_known_entity_names(db: AsyncSession) -> set[str]:
    result = await db.execute(select(Entity.standard_name))
    return {row[0] for row in result.all()}


def build_llm_prompt(
    batch: list[ExtractCandidate],
    known_names: set[str],
) -> str:
    items = "\n".join(
        f"  [{c.id}] content={c.content!r} source={c.source or 'unknown'} confidence={c.confidence}"
        for c in batch
    )
    return (
        LLM_JUDGE_PROMPT.format(
            allowed_types=", ".join(get_llm_allowed_types()),
            blocked_types="concept, other, unknown",
            known_entities=", ".join(sorted(known_names)) if known_names else "(none yet)",
        )
        + f"\n\nCandidates to judge:\n{items}"
    )


async def call_llm(prompt: str, model_id: str = "gemma-4") -> LlmBatchResult:
    try:
        from app.services.agent.gateway.router import route_and_send

        response = await route_and_send(
            model_id=model_id,
            messages=[{"role": "system", "content": prompt}],
            response_format=LlmBatchResult,
            temperature=0.1,
        )
        if isinstance(response, dict):
            return LlmBatchResult(**response)
        return response
    except Exception as e:
        logger.warning("LLM call failed, model=%s error=%s", model_id, e)
        return LlmBatchResult()


def service_layer_new_check(
    output: LlmEntityOutput,
    known_names: set[str],
) -> LlmEntityOutput:
    if is_known_entity(output.standard_name, known_names):
        output.is_new = False
    else:
        output.is_new = True
    if is_llm_type_blocked(output.entity_type):
        output.entity_type = "unknown"
        output.is_new = True
    return output


def content_matches(content: str, term: str) -> bool:
    """Exact match after normalization. No fuzzy — LLM must return candidate text verbatim."""
    c = content.strip().lower()
    t = term.strip().lower()
    return c == t
