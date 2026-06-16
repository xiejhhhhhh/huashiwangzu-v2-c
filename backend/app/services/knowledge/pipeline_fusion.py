import logging
import re

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import PageFusion, PageSource

logger = logging.getLogger("pipeline")


def _is_cid_garbage(text: str, threshold: float = 0.6) -> bool:
    if not text or len(text) < 5:
        return False
    cid_chars = len(re.findall(r"\(cid:\d+\)", text))
    return (cid_chars * 10) / len(text) > threshold


def _build_summary(script_text: str, ocr_text: str, vision_text: str, layout_data: dict) -> str | None:
    vision_summary = layout_data.get("summary") or vision_text
    if vision_summary and len(vision_summary) > 20:
        return vision_summary[:500]
    best = script_text or ocr_text or vision_text or ""
    return best[:200] if best else None


def _collect_page_parts(page_sources: list[PageSource]) -> tuple[str, str | None, dict]:
    script_text, ocr_text, vision_text, layout_data = "", "", "", {}
    for source in page_sources:
        content = source.content or {}
        if source.source_type == "script":
            script_text = content.get("text", "")
        elif source.source_type == "ocr":
            ocr_text = content.get("text", "")
        elif source.source_type == "vision":
            vision_text = content.get("summary", "")
        elif source.source_type == "layout":
            layout_data = content
    if script_text and _is_cid_garbage(script_text):
        script_text = ""
    fused_text = "\n".join(filter(None, [script_text, ocr_text, vision_text])).strip()
    if not fused_text:
        fused_text = layout_data.get("text", "")
    summary = _build_summary(script_text, ocr_text, vision_text, layout_data)
    evidence = {"sources": [source.source_type for source in page_sources]}
    return fused_text, summary, evidence


async def _has_existing_fusion(db: AsyncSession, catalog_id: int, page_num: int) -> bool:
    result = await db.execute(select(PageFusion).where(and_(
        PageFusion.catalog_id == catalog_id,
        PageFusion.page_num == page_num,
    )))
    return result.scalar_one_or_none() is not None


async def layer_fuse(db: AsyncSession, catalog_id: int) -> dict:
    result = await db.execute(
        select(PageSource)
        .where(PageSource.catalog_id == catalog_id)
        .order_by(PageSource.page_num, PageSource.source_type)
    )
    sources = result.scalars().all()
    if not sources:
        logger.warning("No page sources found for catalog %d", catalog_id)
        return {"fused": 0, "skipped": 0}

    page_map: dict[int, list[PageSource]] = {}
    for source in sources:
        page_map.setdefault(source.page_num, []).append(source)

    fused = skipped = 0
    for page_num, page_sources in page_map.items():
        if await _has_existing_fusion(db, catalog_id, page_num):
            skipped += 1
            continue
        fused_text, summary, evidence = _collect_page_parts(page_sources)
        db.add(PageFusion(
            catalog_id=catalog_id,
            page_num=page_num,
            fusion_text=fused_text[:50000] if fused_text else None,
            summary=summary,
            attributes=None,
            labels=None,
            evidence=evidence or None,
            conflicts=None,
            quality_score=None,
        ))
        fused += 1

    await db.commit()
    logger.info("Fused %d pages (skipped %d existing) for catalog %d", fused, skipped, catalog_id)
    return {"fused": fused, "skipped": skipped}
