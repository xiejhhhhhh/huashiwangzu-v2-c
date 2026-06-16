"""
L2 page-level fusion — main orchestration
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.knowledge import PageSource, PageFusion
from app.services.knowledge.fusion.verify import verify_page
from app.services.knowledge.fusion.subject import discover_subjects
from app.services.knowledge.fusion.conflict import detect_conflicts
from app.services.knowledge.fusion.helpers import (
    estimate_quality,
    extract_attributes,
    sources_to_evidence,
    summarize_text,
)

logger = logging.getLogger(__name__)


class FusionService:

    @staticmethod
    async def fuse_page(
        db: AsyncSession,
        catalog_id: int,
        page_num: int,
        use_llm: bool = False,
    ) -> PageFusion:
        result = await db.execute(
            select(PageSource)
            .where(PageSource.catalog_id == catalog_id)
            .where(PageSource.page_num == page_num)
        )
        page_sources = result.scalars().all()
        if not page_sources:
            raise ValueError(f"No page sources found for catalog={catalog_id} page={page_num}")

        source_dicts = [
            {
                "id": s.id,
                "catalog_id": s.catalog_id,
                "page_num": s.page_num,
                "source_type": s.source_type,
                "content": s.content,
                "screenshot_md5": s.screenshot_md5,
                "verify_status": s.verify_status,
            }
            for s in page_sources
        ]

        fusion_text, verify_conflicts = verify_page(source_dicts)

        subject_candidates = discover_subjects(fusion_text, source_dicts, use_llm=use_llm)

        attr_candidates: list[dict] = extract_attributes(fusion_text, subject_candidates)

        extra_conflicts = detect_conflicts(fusion_text, source_dicts, subject_candidates, attr_candidates)
        all_conflicts = verify_conflicts + extra_conflicts

        evidence = sources_to_evidence(source_dicts)

        summary = summarize_text(fusion_text) if fusion_text else ""

        quality_score = estimate_quality(fusion_text, all_conflicts, subject_candidates)

        labels = [
            {"label": s["name"], "category": s.get("subject_type", ""), "source": s.get("source", "rule")}
            for s in subject_candidates
        ]

        stmt = pg_insert(PageFusion).values(
            catalog_id=catalog_id,
            page_num=page_num,
            fusion_text=fusion_text,
            summary=summary,
            attributes=attr_candidates,
            labels=labels,
            evidence=evidence,
            conflicts=[c.to_dict() for c in all_conflicts],
            quality_score=quality_score,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_page_fusion",
            set_={
                "fusion_text": fusion_text,
                "summary": summary,
                "attributes": attr_candidates,
                "labels": labels,
                "evidence": evidence,
                "conflicts": [c.to_dict() for c in all_conflicts],
                "quality_score": quality_score,
            },
        )
        await db.execute(stmt)
        await db.commit()

        result = await db.execute(
            select(PageFusion)
            .where(PageFusion.catalog_id == catalog_id)
            .where(PageFusion.page_num == page_num)
        )
        return result.scalar_one()

    @staticmethod
    async def fuse_catalog(
        db: AsyncSession,
        catalog_id: int,
        use_llm: bool = False,
    ) -> list[PageFusion]:
        result = await db.execute(
            select(PageSource.catalog_id, PageSource.page_num)
            .where(PageSource.catalog_id == catalog_id)
            .distinct()
        )
        pages = result.all()

        fusions: list[PageFusion] = []
        for catalog_id_val, page_num_val in pages:
            try:
                fusion = await FusionService.fuse_page(db, catalog_id_val, page_num_val, use_llm=use_llm)
                fusions.append(fusion)
            except Exception as e:
                logger.exception("Fusion failed for catalog=%d page=%d", catalog_id_val, page_num_val)
        return fusions
