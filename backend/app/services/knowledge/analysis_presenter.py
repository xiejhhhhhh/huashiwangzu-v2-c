from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Catalog, Label, PageFusion, PageSource


def _source_dict(source: PageSource) -> dict:
    return {
        "id": source.id, "pageNum": source.page_num,
        "sourceType": source.source_type, "content": source.content,
        "screenshotMd5": source.screenshot_md5,
        "verifyStatus": source.verify_status,
    }


def _fusion_dict(fusion: PageFusion) -> dict:
    return {
        "id": fusion.id, "pageNum": fusion.page_num,
        "summary": fusion.summary, "fusionText": fusion.fusion_text,
        "attributes": fusion.attributes, "labels": fusion.labels,
        "evidence": fusion.evidence, "conflicts": fusion.conflicts,
        "qualityScore": fusion.quality_score,
    }


def _label_dict(label: Label) -> dict:
    return {
        "id": label.id, "targetType": label.target_type,
        "targetId": label.target_id, "label": label.label,
        "category": label.label_category,
        "passedAdmission": label.passed_admission,
    }


async def build_analysis_result(
    db: AsyncSession,
    catalog: Catalog,
    include_sources: bool = True,
    limit: int = 100,
) -> dict:
    sources = (await db.execute(
        select(PageSource).where(PageSource.catalog_id == catalog.id)
        .order_by(PageSource.page_num, PageSource.source_type).limit(limit)
    )).scalars().all()
    fusions = (await db.execute(
        select(PageFusion).where(PageFusion.catalog_id == catalog.id).order_by(PageFusion.page_num).limit(limit)
    )).scalars().all()
    labels = (await db.execute(
        select(Label).where(Label.target_type == "file", Label.target_id == catalog.id).order_by(Label.id)
    )).scalars().all()
    source_counts: dict[str, int] = {}
    for source in sources:
        source_counts[source.source_type] = source_counts.get(source.source_type, 0) + 1
    return {
        "catalog": {
            "id": catalog.id, "fileName": catalog.file_name,
            "mimeType": catalog.mime_type, "channelType": catalog.channel_type,
            "status": catalog.status, "error": catalog.error,
        },
        "sourceCounts": source_counts,
        "visionStats": {
            "pageCount": len({s.page_num for s in sources}),
            "visionPageCount": source_counts.get("vision", 0),
            "layoutPageCount": source_counts.get("layout", 0),
        },
        "pageSources": [_source_dict(source) for source in sources] if include_sources else [],
        "pageFusions": [_fusion_dict(fusion) for fusion in fusions],
        "labels": [_label_dict(label) for label in labels],
    }
