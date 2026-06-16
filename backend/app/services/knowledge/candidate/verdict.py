"""Verdict orchestrator — runs L0→L4 pipeline on pending candidates."""

import logging
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.knowledge.candidate.l0_ignore import run_l0_ignore
from app.services.knowledge.candidate.l1_merge import run_l1_merge
from app.services.knowledge.candidate.l2_pass import run_l2_pass
from app.services.knowledge.candidate.l3_llm import run_l3_llm
from app.models.knowledge.candidate import ExtractCandidate

logger = logging.getLogger(__name__)


async def run_governance_pipeline(
    db: AsyncSession,
    l3_enabled: bool = True,
    l3_batch_size: int = 50,
) -> dict[str, Any]:
    """Run full L0→L4 pipeline. L4 (manual review) is not handled here."""
    report: dict[str, Any] = {
        "l0_ignored": 0,
        "l1_merged": 0,
        "l2_passed": {},
        "l3_processed": {},
        "remaining_pending": 0,
    }

    # L0: auto-ignore
    l0_count = await run_l0_ignore(db)
    report["l0_ignored"] = l0_count
    logger.info("L0 ignored %d candidates", l0_count)

    # L1: auto-merge
    l1_count = await run_l1_merge(db)
    report["l1_merged"] = l1_count
    logger.info("L1 merged %d candidates", l1_count)

    # L2: auto-pass
    l2_stats = await run_l2_pass(db)
    report["l2_passed"] = l2_stats
    logger.info("L2 stats: %s", l2_stats)

    # L3: LLM batch judgment
    if l3_enabled:
        l3_stats = await run_l3_llm(db, batch_size=l3_batch_size)
        report["l3_processed"] = l3_stats
        logger.info("L3 stats: %s", l3_stats)

    # Count remaining
    from sqlalchemy import select, func
    result = await db.execute(
        select(func.count()).select_from(ExtractCandidate).where(
            ExtractCandidate.verdict_status == 0
        )
    )
    report["remaining_pending"] = result.scalar() or 0
    logger.info("Remaining pending: %d", report["remaining_pending"])

    return report
