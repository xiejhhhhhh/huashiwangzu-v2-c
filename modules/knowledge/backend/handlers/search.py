"""Search-related endpoints (search, entities, entity-dictionary, graph-context, export)."""
import logging
from typing import Literal

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.cognitive_index_service import persist_query_context
from ..services.document_service import get_document
from ..services.embedding_service import get_chunk_by_id
from ..services.entity_service import get_entity_dictionary, get_graph_context, get_page_fusion
from ..services.governance_service import get_evidence_detail
from ..services.search_service import get_document_chunks, hybrid_search
from ..services.source_file_state import get_live_document_or_raise

logger = logging.getLogger("v2.knowledge").getChild("handlers.search")

sub_router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    use_rerank: bool = True  # 默认开重排:rerank()是真bge-reranker,之前默认关导致召回不精
    embedding_profile: str | None = None


class ExportRequest(BaseModel):
    document_id: int
    format: Literal["markdown", "html", "json"] = "markdown"


@sub_router.post("/search")
async def api_search(
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    from ..router import _enrich_search_results

    results = await hybrid_search(
        db,
        payload.query,
        user.id,
        payload.top_k,
        payload.use_rerank,
        embedding_profile=payload.embedding_profile,
    )
    enriched, context_data = await _enrich_search_results(db, results, user.id)
    query_context = await persist_query_context(
        db,
        owner_id=user.id,
        query=payload.query,
        results=enriched,
        query_plan=getattr(results, "query_plan", None),
        diagnostics=getattr(results, "diagnostics", None),
    )
    await db.commit()
    return ApiResponse(data={
        "query": payload.query,
        "results": enriched,
        "context_data": {
            **context_data,
            "top_k": payload.top_k,
            "use_rerank": payload.use_rerank,
            "query_plan": getattr(results, "query_plan", None),
            "diagnostics": getattr(results, "diagnostics", None),
            "query_context": query_context,
        },
    })


@sub_router.get("/documents/{document_id}/chunks")
async def api_document_chunks(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await get_live_document_or_raise(db, document_id, user.id)
    result = await get_document_chunks(db, document_id, owner_id=user.id)
    return ApiResponse(data=result)


@sub_router.get("/chunks/{chunk_id}")
async def api_get_chunk(
    chunk_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await get_chunk_by_id(db, chunk_id, owner_id=user.id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Chunk not found")
    return ApiResponse(data=result)


@sub_router.get("/documents/{document_id}/page/{page}")
async def api_get_page_fusion(
    document_id: int,
    page: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    doc = await get_live_document_or_raise(db, document_id, user.id)
    result = await get_page_fusion(db, document_id, page, owner_id=int(doc["owner_id"]))
    return ApiResponse(data=result)


@sub_router.get("/entities")
async def api_entities(
    keyword: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await get_entity_dictionary(db, user.id, keyword)
    return ApiResponse(data=result)


@sub_router.get("/entities/{entity_id}/graph")
async def api_graph_context(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await get_graph_context(db, user.id, entity_id)
    return ApiResponse(data=result)


@sub_router.get("/entities/{entity_id}/evidence")
async def api_evidence_detail(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await get_evidence_detail(db, user.id, entity_id)
    return ApiResponse(data=result)


@sub_router.get("/entity-graph")
async def api_entity_graph(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """获取实体级知识图谱（节点=实体/概念/标签，边=关系）。"""
    from ..models import KbGraphEdge, KbGraphNode
    node_r = await db.execute(
        select(KbGraphNode).where(KbGraphNode.owner_id == user.id).limit(200)
    )
    nodes = node_r.scalars().all()
    node_ids = [n.id for n in nodes]
    edges_list: list[dict] = []
    if node_ids:
        edge_r = await db.execute(
            select(KbGraphEdge).where(
                KbGraphEdge.owner_id == user.id,
                KbGraphEdge.source_node_id.in_(node_ids),
                KbGraphEdge.target_node_id.in_(node_ids),
            ).limit(500)
        )
        for e in edge_r.scalars().all():
            edges_list.append({
                "source": e.source_node_id,
                "target": e.target_node_id,
                "relation": e.relation,
                "weight": e.weight,
                "description": e.description,
            })
    return ApiResponse(data={
        "nodes": [{"id": n.id, "label": n.label, "category": n.category, "type": n.category} for n in nodes],
        "edges": edges_list,
    })


@sub_router.post("/documents/export")
async def api_export_document(
    payload: ExportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """Export a parsed document in markdown/html/json format."""
    from ..services.export_service import export_document

    doc = await get_live_document_or_raise(db, payload.document_id, user.id)
    result = await export_document(db, payload.document_id, fmt=payload.format, owner_id=int(doc["owner_id"]))
    if not result.get("success"):
        from app.core.exceptions import NotFound, ValidationError
        if result.get("error", "").startswith("Document not"):
            raise NotFound(result["error"])
        raise ValidationError(result.get("error", "Export failed"))
    return ApiResponse(data=result)

