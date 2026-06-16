import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeTask
from app.services.knowledge.catalog_service import CatalogService
from app.services.knowledge.pipeline import (
    create_next_task,
    create_pipeline_tasks,
    get_next_layer,
    run_full_pipeline,
    run_pipeline_layer,
)

logger = logging.getLogger("knowledge_worker")
HEARTBEAT_INTERVAL = 15
shutdown_requested = False

def request_shutdown() -> None:
    global shutdown_requested
    shutdown_requested = True

async def heartbeat_loop(task_id: int, interval: int = HEARTBEAT_INTERVAL) -> None:
    while not shutdown_requested:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(KnowledgeTask)
                    .where(KnowledgeTask.id == task_id)
                    .values(heartbeat=datetime.now(timezone.utc))
                )
                await db.commit()
        except Exception as e:
            logger.error("Heartbeat update failed: %s", e)
        await asyncio.sleep(interval)

async def acquire_task(db: AsyncSession, lease_minutes: int = 30) -> KnowledgeTask | None:
    now = datetime.now(timezone.utc)
    lease_until = now + timedelta(minutes=lease_minutes)
    task = await _first_available_task(db)
    if task:
        await _lease_task(db, task, lease_until, now)
        return task
    expired = await _first_expired_task(db, now)
    if expired:
        logger.warning("Reclaiming expired task %d", expired.id)
        await _lease_task(db, expired, lease_until, now)
        return expired
    return None

async def _first_available_task(db: AsyncSession) -> KnowledgeTask | None:
    result = await db.execute(
        select(KnowledgeTask)
        .where(KnowledgeTask.status == "pending", KnowledgeTask.lease_until.is_(None))
        .order_by(KnowledgeTask.id)
        .limit(1)
    )
    return result.scalar_one_or_none()

async def _first_expired_task(db: AsyncSession, now: datetime) -> KnowledgeTask | None:
    result = await db.execute(
        select(KnowledgeTask)
        .where(KnowledgeTask.status == "processing", KnowledgeTask.lease_until < now)
        .order_by(KnowledgeTask.id)
        .limit(1)
    )
    return result.scalar_one_or_none()

async def _lease_task(db: AsyncSession, task: KnowledgeTask, lease_until: datetime, now: datetime) -> None:
    task.status = "processing"
    task.lease_until = lease_until
    task.heartbeat = now
    await db.commit()
    await db.refresh(task)

async def release_task(db: AsyncSession, task: KnowledgeTask, success: bool, error: str | None = None) -> None:
    task.status = "done" if success else "failed"
    task.lease_until = None
    if error:
        task.error = error[:2000]
    await db.commit()

async def process_task(db: AsyncSession, task: KnowledgeTask) -> None:
    logger.info("Processing task %d: catalog=%d layer=%s", task.id, task.catalog_id, task.task_type)
    heartbeat = asyncio.create_task(heartbeat_loop(task.id))
    try:
        await _run_task_layer(db, task)
        await release_task(db, task, success=True)
    except Exception as e:
        logger.exception("Task %d failed: %s", task.id, e)
        await release_task(db, task, success=False, error=str(e))
        await CatalogService.update_status(db, task.catalog_id, "failed", error=str(e))
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass

async def _run_task_layer(db: AsyncSession, task: KnowledgeTask) -> None:
    task.progress = 10
    await db.commit()
    if task.task_type == "full":
        result = await run_full_pipeline(db, task.catalog_id)
        logger.info("Full pipeline done for catalog %d: %s", task.catalog_id, result)
        await CatalogService.update_status(db, task.catalog_id, "done")
    else:
        result = await run_pipeline_layer(db, task.catalog_id, task.task_type)
        logger.info("Layer %s done for catalog %d: %s", task.task_type, task.catalog_id, result)
        await _enqueue_next_or_finish(db, task)
    task.progress = 100
    await db.commit()

async def _enqueue_next_or_finish(db: AsyncSession, task: KnowledgeTask) -> None:
    next_layer = get_next_layer(task.task_type)
    if next_layer:
        await create_next_task(db, task.catalog_id, next_layer)
    else:
        await CatalogService.update_status(db, task.catalog_id, "done")

async def main_loop(interval: int = 15, lease_minutes: int = 30, once: bool = False) -> None:
    logger.info("Knowledge worker started (interval=%ds, lease=%dmin)", interval, lease_minutes)
    while not shutdown_requested:
        await _process_one_cycle(lease_minutes, once)
        if once:
            break
        await _sleep_between_cycles(interval)

async def _process_one_cycle(lease_minutes: int, once: bool) -> None:
    try:
        async with AsyncSessionLocal() as db:
            task = await acquire_task(db, lease_minutes=lease_minutes)
            if task:
                await process_task(db, task)
            elif once:
                logger.info("No pending tasks, exiting")
    except Exception as e:
        logger.exception("Worker loop error: %s", e)

async def _sleep_between_cycles(interval: int) -> None:
    for _ in range(interval * 2):
        if shutdown_requested:
            break
        await asyncio.sleep(0.5)

async def process_catalog(catalog_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await create_pipeline_tasks(db, catalog_id)
    async with AsyncSessionLocal() as db:
        task = await acquire_task(db, lease_minutes=60)
        while task:
            await process_task(db, task)
            task = await acquire_task(db, lease_minutes=60)
