import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge import PageFusion, PageSource
from app.schemas.knowledge import PageFusionResult, EvidenceSource

logger = logging.getLogger(__name__)


async def get_page_fusion(
    db: AsyncSession,
    fusion_id: int | None = None,
    catalog_id: int | None = None,
    page_num: int | None = None,
    offset: int = 0,
    limit: int = 2000,
) -> PageFusionResult | None:
    if fusion_id is not None:
        stmt = select(PageFusion).where(PageFusion.id == fusion_id)
    elif catalog_id is not None and page_num is not None:
        stmt = (
            select(PageFusion)
            .where(PageFusion.catalog_id == catalog_id)
            .where(PageFusion.page_num == page_num)
        )
    else:
        return None

    result = await db.execute(stmt)
    fusion = result.scalar_one_or_none()
    if not fusion:
        return None

    fusion_text = fusion.fusion_text
    if fusion_text and (offset > 0 or limit > 0):
        fusion_text = fusion_text[offset:offset + limit]

    from app.models.knowledge import Catalog
    cat_stmt = select(Catalog).where(Catalog.id == fusion.catalog_id)
    cat_result = await db.execute(cat_stmt)
    cat = cat_result.scalar_one_or_none()
    file_name = cat.file_name if cat else None

    sources = await get_page_sources(db, fusion.catalog_id, fusion.page_num)

    return PageFusionResult(
        fusion_id=fusion.id,
        catalog_id=fusion.catalog_id,
        page_num=fusion.page_num,
        file_name=file_name,
        fusion_text=fusion_text,
        summary=fusion.summary,
        attributes=fusion.attributes,
        labels=fusion.labels,
        evidence=fusion.evidence,
        conflicts=fusion.conflicts,
        quality_score=fusion.quality_score,
        original_sources=sources,
    )


async def get_page_fusion_by_ids(
    db: AsyncSession,
    fusion_ids: list[int],
    offset: int = 0,
    limit: int = 2000,
) -> list[PageFusionResult]:
    results = []
    for fid in fusion_ids:
        item = await get_page_fusion(db, fusion_id=fid, offset=offset, limit=limit)
        if item:
            results.append(item)
    return results


async def get_page_sources(
    db: AsyncSession,
    catalog_id: int,
    page_num: int,
) -> list[EvidenceSource]:
    stmt = (
        select(PageSource)
        .where(PageSource.catalog_id == catalog_id)
        .where(PageSource.page_num == page_num)
    )
    result = await db.execute(stmt)
    sources = result.scalars().all()

    return [
        EvidenceSource(
            source_type=s.source_type,
            content=str(s.content)[:500] if s.content else None,
            screenshot_md5=s.screenshot_md5,
        )
        for s in sources
    ]
