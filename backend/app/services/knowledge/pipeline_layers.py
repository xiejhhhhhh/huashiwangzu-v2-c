import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Catalog, Chunk, Entity, ExtractCandidate, GraphNode, Label
from app.services.knowledge.chunk_service import ChunkService
from app.services.knowledge.embedding_service import EmbeddingService
from app.services.knowledge.extract.dispatch import ExtractDispatcher
from app.services.knowledge.pipeline_fusion import layer_fuse

logger = logging.getLogger("pipeline")


class PipelineError(Exception):
    pass


async def layer_extract(db: AsyncSession, catalog_id: int) -> None:
    result = await db.execute(select(Catalog).where(Catalog.id == catalog_id))
    catalog = result.scalar_one_or_none()
    if not catalog:
        raise PipelineError(f"Catalog {catalog_id} not found")
    await ExtractDispatcher.dispatch(db, catalog)


async def layer_chunk(db: AsyncSession, catalog_id: int) -> dict:
    chunks = await ChunkService.chunk_all_fusions(db, catalog_id=catalog_id)
    return {"chunks": len(chunks)}


async def layer_vectorize(db: AsyncSession, catalog_id: int) -> dict:
    count = await EmbeddingService.vectorize_chunks_batch(db, catalog_id=catalog_id)
    return {"vectorized": count}


async def _has_candidates(db: AsyncSession, catalog_id: int) -> bool:
    result = await db.execute(
        select(ExtractCandidate.id)
        .where(ExtractCandidate.source.like(f"catalog:{catalog_id}/%"))
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _candidate_from_chunk(catalog_id: int, chunk: Chunk) -> ExtractCandidate | None:
    text = chunk.content[:200]
    if not text.strip():
        return None
    return ExtractCandidate(
        content=text,
        source=f"catalog:{catalog_id}/chunk:{chunk.id}",
        evidence_page=str(chunk.page_num) if chunk.page_num else None,
        confidence=0.5,
        verdict_status=0,
    )


async def layer_candidate(db: AsyncSession, catalog_id: int) -> dict:
    if await _has_candidates(db, catalog_id):
        return {"candidates": 0, "note": f"catalog {catalog_id} candidates already exist, skip"}
    chunks = await ChunkService.get_chunks_by_catalog(db, catalog_id)
    candidates_created = 0
    for chunk in chunks:
        candidate = _candidate_from_chunk(catalog_id, chunk)
        if not candidate:
            continue
        db.add(candidate)
        candidates_created += 1
    await db.commit()
    logger.info("Created %d candidates for catalog %d", candidates_created, catalog_id)
    return {"candidates": candidates_created}


async def layer_resolve(db: AsyncSession, catalog_id: int) -> dict:
    result = await db.execute(select(Entity).where(Entity.confirm_status == "confirmed").limit(50))
    nodes = labels = 0
    for entity in result.scalars().all():
        existing = await db.execute(select(GraphNode).where(GraphNode.entity_id == entity.id))
        if existing.first():
            continue
        db.add(GraphNode(
            entity_id=entity.id,
            node_type=entity.entity_type,
            occurrence_count=entity.occurrence_count or 1,
        ))
        db.add(Label(
            target_type="entity",
            target_id=entity.id,
            label=entity.standard_name,
            label_category=entity.entity_type,
            passed_admission=True,
        ))
        nodes += 1
        labels += 1
    if nodes or labels:
        await db.commit()
    total_nodes = await db.scalar(select(func.count(GraphNode.id)))
    logger.info("Resolve for catalog %d: %d new nodes, %d new labels", catalog_id, nodes, labels)
    return {"nodes": nodes, "labels": labels, "total_nodes": total_nodes}


LAYER_MAP = {
    "extract": layer_extract,
    "fuse": layer_fuse,
    "chunk": layer_chunk,
    "vectorize": layer_vectorize,
    "candidate": layer_candidate,
    "resolve": layer_resolve,
}
