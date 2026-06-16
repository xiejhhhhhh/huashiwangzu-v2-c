import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    DisambigCandidate,
)
from app.services.knowledge.aggregation.merge_ops import execute_merge, rollback_merge

logger = logging.getLogger(__name__)


MERGE_CONFIDENCE_AUTO = 0.95
MERGE_CONFIDENCE_PENDING = 0.8


class MergeService:

    @staticmethod
    async def process_candidates(db: AsyncSession, dry_run: bool = False) -> dict:
        """读取消歧候选, 按置信度自动/待审核/忽略"""
        result = await db.execute(
            select(DisambigCandidate).where(DisambigCandidate.review_status == "pending")
        )
        candidates = result.scalars().all()

        stats = {"auto_merged": 0, "marked_pending": 0, "ignored": 0, "errors": []}

        for c in candidates:
            try:
                if c.confidence >= MERGE_CONFIDENCE_AUTO:
                    if not dry_run:
                        await execute_merge(db, c.entity_a_id, c.entity_b_id, c.confidence)
                        c.review_status = "approved"
                    stats["auto_merged"] += 1
                elif c.confidence >= MERGE_CONFIDENCE_PENDING:
                    if not dry_run:
                        c.review_status = "pending"
                    stats["marked_pending"] += 1
                else:
                    if not dry_run:
                        c.review_status = "rejected"
                    stats["ignored"] += 1
            except Exception as e:
                logger.exception("Merge failed for candidate %d", c.id)
                stats["errors"].append({"candidate_id": c.id, "error": str(e)})

        if not dry_run:
            await db.commit()

        return stats

    @staticmethod
    async def rollback(db: AsyncSession, merge_record_id: int) -> bool:
        """根据 merge 记录回滚一次合并"""
        ok = await rollback_merge(db, merge_record_id)
        logger.info("Rollback merge record %d done: %s", merge_record_id, ok)
        return ok
