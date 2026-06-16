import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeTask

logger = logging.getLogger("pipeline")


def get_next_layer(order: list[str], current_layer: str) -> str | None:
    try:
        idx = order.index(current_layer)
    except ValueError:
        return None
    return order[idx + 1] if idx + 1 < len(order) else None


async def create_pipeline_tasks(
    db: AsyncSession, catalog_id: int, order: list[str]
) -> KnowledgeTask:
    result = await db.execute(select(KnowledgeTask).where(
        KnowledgeTask.catalog_id == catalog_id,
        KnowledgeTask.status == "pending",
    ))
    for task in result.scalars().all():
        task.status = "cancelled"

    first_layer = order[0]
    task = KnowledgeTask(
        catalog_id=catalog_id,
        task_type=first_layer,
        status="pending",
        progress=0,
    )
    db.add(task)
    await db.commit()
    logger.info("Created pipeline task %s for catalog %d", first_layer, catalog_id)
    return task


async def create_next_task(
    db: AsyncSession, catalog_id: int, next_layer: str
) -> KnowledgeTask | None:
    existing = await db.execute(select(KnowledgeTask).where(
        KnowledgeTask.catalog_id == catalog_id,
        KnowledgeTask.task_type == next_layer,
        KnowledgeTask.status.in_(["pending", "processing"]),
    ))
    if existing.scalar_one_or_none():
        return None
    task = KnowledgeTask(
        catalog_id=catalog_id,
        task_type=next_layer,
        status="pending",
        progress=0,
    )
    db.add(task)
    await db.commit()
    return task
