from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Catalog, KnowledgeTask, PageSource
from app.services.model_watchdog.registry import list_models
from app.services.model_watchdog.watchdog import status_all

VISION_CHANNELS = ("pdf", "image")


async def provider_status() -> dict:
    statuses = status_all()
    providers = []
    for record in list_models():
        if record.purpose != "视觉":
            continue
        providers.append({
            "name": record.name,
            "type": record.model_type,
            "endpoint": record.endpoint,
            "healthy": bool(statuses.get(record.name)),
            "description": record.description,
        })
    return {"providers": providers}


async def extraction_stats(db: AsyncSession) -> dict:
    catalog_count = await db.scalar(
        select(func.count()).select_from(Catalog).where(Catalog.channel_type.in_(VISION_CHANNELS))
    ) or 0
    vision_pages = await db.scalar(
        select(func.count()).select_from(PageSource).where(PageSource.source_type == "vision")
    ) or 0
    pending_tasks = await db.scalar(
        select(func.count()).select_from(KnowledgeTask).where(
            KnowledgeTask.task_type == "extract",
            KnowledgeTask.status.in_(("pending", "processing")),
        )
    ) or 0
    return {"catalogCount": catalog_count, "visionPageCount": vision_pages, "activeExtractTasks": pending_tasks}


async def catalog_status(db: AsyncSession, catalog_id: int) -> dict | None:
    catalog = await db.get(Catalog, catalog_id)
    if not catalog:
        return None
    total_pages = await _page_count(db, catalog_id)
    vision_pages = await _page_count(db, catalog_id, source_type="vision")
    task = await _latest_extract_task(db, catalog_id)
    return {
        "catalogId": catalog.id,
        "fileName": catalog.file_name,
        "channelType": catalog.channel_type,
        "catalogStatus": catalog.status,
        "totalPages": total_pages,
        "visionPages": vision_pages,
        "lastExtractTask": _task_dict(task) if task else None,
    }


async def dry_run(db: AsyncSession, limit: int = 20) -> dict:
    result = await db.execute(
        select(Catalog).where(Catalog.channel_type.in_(VISION_CHANNELS)).order_by(desc(Catalog.id)).limit(limit)
    )
    items = []
    for catalog in result.scalars().all():
        total = await _page_count(db, catalog.id)
        vision = await _page_count(db, catalog.id, source_type="vision")
        items.append({"catalogId": catalog.id, "fileName": catalog.file_name, "plannedPages": max(total - vision, 0)})
    return {"items": items, "limit": limit}


async def _page_count(db: AsyncSession, catalog_id: int, source_type: str | None = None) -> int:
    stmt = select(func.count(func.distinct(PageSource.page_num))).where(PageSource.catalog_id == catalog_id)
    if source_type:
        stmt = stmt.where(PageSource.source_type == source_type)
    return await db.scalar(stmt) or 0


async def _latest_extract_task(db: AsyncSession, catalog_id: int) -> KnowledgeTask | None:
    result = await db.execute(
        select(KnowledgeTask).where(
            KnowledgeTask.catalog_id == catalog_id,
            KnowledgeTask.task_type == "extract",
        ).order_by(desc(KnowledgeTask.id)).limit(1)
    )
    return result.scalar_one_or_none()


def _task_dict(task: KnowledgeTask) -> dict:
    return {"id": task.id, "status": task.status, "progress": task.progress, "error": task.error}
