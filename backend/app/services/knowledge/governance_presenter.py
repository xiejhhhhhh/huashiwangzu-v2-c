from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Entity, Evidence, ExtractCandidate, GraphEdge, GraphNode


def page_bounds(page: int, page_size: int) -> tuple[int, int]:
    return max(page, 1), min(max(page_size, 1), 100)


async def paginate(db: AsyncSession, query, page: int, page_size: int) -> dict:
    page, page_size = page_bounds(page, page_size)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    return {"items": result.scalars().all(), "total": total or 0, "page": page, "pageSize": page_size}


def _time(value) -> str | None:
    return value.isoformat() if value else None


def evidence_dict(e: Evidence) -> dict:
    return {
        "id": e.id, "sourceType": e.source_type, "sourceId": e.source_id,
        "catalogId": e.catalog_id, "pageNum": e.page_num,
        "confidence": e.confidence, "crossVerified": e.cross_verified,
        "boundConclusions": e.bound_conclusions,
        "createdAt": _time(e.created_at),
    }


def candidate_dict(c: ExtractCandidate) -> dict:
    return {
        "id": c.id, "content": c.content, "source": c.source,
        "evidencePage": c.evidence_page, "confidence": c.confidence,
        "verdictStatus": c.verdict_status, "extra": c.extra,
        "createdAt": _time(c.created_at),
    }


def node_dict(n: GraphNode) -> dict:
    return {
        "id": n.id, "entityId": n.entity_id, "nodeType": n.node_type,
        "occurrenceCount": n.occurrence_count, "createdAt": _time(n.created_at),
    }


def edge_dict(e: GraphEdge) -> dict:
    return {
        "id": e.id, "fromNodeId": e.from_node_id, "toNodeId": e.to_node_id,
        "relation": e.relation, "supportChunkIds": e.support_chunk_ids,
        "weight": e.weight, "createdAt": _time(e.created_at),
    }


def entity_dict(e: Entity) -> dict:
    return {
        "id": e.id, "standardName": e.standard_name, "entityType": e.entity_type,
        "confirmStatus": e.confirm_status, "occurrenceCount": e.occurrence_count,
    }
