import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeTask
from app.services.knowledge.pipeline_layers import LAYER_MAP, PipelineError
from app.services.knowledge.pipeline_tasks import (
    create_next_task as _create_next_task,
    create_pipeline_tasks as _create_pipeline_tasks,
    get_next_layer as _get_next_layer,
)

logger = logging.getLogger("pipeline")

PIPELINE_ORDER = ["extract", "fuse", "chunk", "vectorize", "candidate", "resolve"]


async def run_pipeline_layer(db: AsyncSession, catalog_id: int, layer: str) -> dict:
    handler = LAYER_MAP.get(layer)
    if not handler:
        raise PipelineError(f"Unknown layer: {layer}")
    return await handler(db, catalog_id)


async def run_full_pipeline(db: AsyncSession, catalog_id: int) -> dict:
    results = {}
    for layer in PIPELINE_ORDER:
        logger.info("Starting layer %s for catalog %d", layer, catalog_id)
        try:
            result = await run_pipeline_layer(db, catalog_id, layer)
            results[layer] = result
            logger.info("Layer %s done: %s", layer, result)
        except Exception as e:
            logger.exception("Layer %s failed for catalog %d: %s", layer, catalog_id, e)
            results[layer] = {"error": str(e)}
            raise PipelineError(f"Pipeline failed at layer {layer}: {e}") from e
    return results


def get_next_layer(current_layer: str) -> str | None:
    return _get_next_layer(PIPELINE_ORDER, current_layer)


async def create_pipeline_tasks(db: AsyncSession, catalog_id: int) -> KnowledgeTask:
    return await _create_pipeline_tasks(db, catalog_id, PIPELINE_ORDER)


async def create_next_task(db: AsyncSession, catalog_id: int, next_layer: str) -> KnowledgeTask | None:
    return await _create_next_task(db, catalog_id, next_layer)
