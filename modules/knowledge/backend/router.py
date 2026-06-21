"""FastAPI router for knowledge module.

业务接口全部在模块内；对外能力通过框架 register_capability 注册，供 Agent 自动发现和调用。
"""
import logging
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability

from .document_service import (
    register_document, list_documents, get_document, soft_delete_document,
    parse_and_index_document, resolve_user_id,
)
from .embedding_service import get_chunk_by_id
from .search_service import hybrid_search, get_document_chunks
from .entity_service import get_entity_dictionary, get_graph_context, get_page_fusion, process_document_entities_from_fusions
from .governance_service import (
    list_governance_candidates, approve_candidate, reject_candidate,
    merge_entities, get_pending_count, get_evidence_detail, calibrate_extraction,
)
from .raw_collection_service import (
    get_raw_data,
)
from .fusion_service import (
    get_page_fusion_detail,
)
from .init_db import _run_startup_init
from .profile_service import get_document_profile
from .relation_service import get_file_relations, get_relation_graph
from .progress_service import get_document_progress, list_documents_progress
from . import pipeline_service  # noqa: F401 注册 kb_pipeline handler

logger = logging.getLogger("v2.knowledge")
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# ── 模块加载时初始化：建表 + 索引 + 列迁移（一次性，幂等） ──
_run_startup_init()


class RegisterDocumentRequest(BaseModel):
    file_id: int
    catalog_id: int | None = None


class ParseDocumentRequest(BaseModel):
    document_id: int
    extract_graph: bool = True


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    use_rerank: bool = False


class MergeEntitiesRequest(BaseModel):
    source_entity_ids: list[int]
    target_entity_id: int
    reason: str = ""


class CalibrateRequest(BaseModel):
    candidate_id: int
    new_name: str | None = None
    new_category: str | None = None


class CollectRawRequest(BaseModel):
    document_id: int


class FuseRequest(BaseModel):
    document_id: int


class ProfileRequest(BaseModel):
    document_id: int
    force_raw: bool = False
    force_fusion: bool = False


class RelationComputeRequest(BaseModel):
    document_id: int


class ProgressBatchRequest(BaseModel):
    document_ids: list[int] = Field(default_factory=list)


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "knowledge", "status": "ok"})


@router.post("/documents")
async def api_register_document(
    payload: RegisterDocumentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await register_document(db, payload.file_id, user.id, payload.catalog_id)
    return ApiResponse(data=result)


@router.get("/documents")
async def api_list_documents(
    catalog_id: int | None = Query(default=None),
    keyword: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await list_documents(db, user.id, catalog_id, keyword, page, page_size)
    return ApiResponse(data=result)


@router.get("/documents/{document_id}")
async def api_get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await get_document(db, document_id, user.id)
    return ApiResponse(data=result)


@router.delete("/documents/{document_id}")
async def api_delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    await soft_delete_document(db, document_id, user.id)
    return ApiResponse(data={"deleted": True})


@router.post("/documents/parse")
async def api_parse_document(
    payload: ParseDocumentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await parse_and_index_document(
        db,
        payload.document_id,
        user.id,
        caller=f"user:{user.id}",
        extract_graph=payload.extract_graph,
    )
    return ApiResponse(data=result)


@router.post("/documents/collect-raw")
async def api_collect_raw(
    payload: CollectRawRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """触发原始层多轮采集（后台任务）。"""
    from app.models.system import SystemTaskQueue
    from .models import KbDocument
    import json as _json

    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == payload.document_id,
            KbDocument.owner_id == user.id,
            KbDocument.deleted == False,
        )
    )
    doc = r.scalar_one_or_none()
    if not doc:
        from app.core.exceptions import NotFound
        raise NotFound("Document not found")

    task = SystemTaskQueue(
        task_type="kb_collect_raw",
        module="knowledge",
        parameters=_json.dumps({"document_id": payload.document_id}, ensure_ascii=False),
        priority=5,
        status="pending",
        creator_id=user.id,
    )
    db.add(task)
    await db.commit()
    return ApiResponse(data={"task_id": task.id, "status": "enqueued"})


@router.get("/documents/{document_id}/raw-status")
async def api_raw_status(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    doc = await get_document(db, document_id, user.id)
    return ApiResponse(data={"document_id": document_id, "raw_status": doc.get("raw_status", doc.get("parse_status"))})


@router.get("/documents/{document_id}/raw-data")
async def api_raw_data(
    document_id: int,
    page: int | None = Query(default=None),
    round_num: int | None = Query(default=None, alias="round"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await get_document(db, document_id, user.id)
    data = await get_raw_data(db, document_id, page, round_num)
    return ApiResponse(data={"raw_data": data})


@router.post("/documents/fuse")
async def api_fuse(
    payload: FuseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """触发页级融合（第4层，后台任务 kb_fuse）。"""
    return await _enqueue_task(db, "kb_fuse", payload.document_id, user.id)


@router.get("/documents/{document_id}/fusion-status")
async def api_fusion_status(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    doc = await get_document(db, document_id, user.id)
    return ApiResponse(data={"document_id": document_id, "fusion_status": doc.get("fusion_status", "pending")})


@router.get("/documents/{document_id}/page-fusion/{page}")
async def api_page_fusion_detail(
    document_id: int,
    page: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await get_document(db, document_id, user.id)
    result = await get_page_fusion_detail(db, document_id, page)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Page fusion not found")
    return ApiResponse(data=result)


@router.get("/documents/{document_id}/fusions")
async def api_list_fusions(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """列出文档所有页的融合内容(第4层,阅读视图用)。"""
    from .models import KbPageFusion
    await get_document(db, document_id, user.id)
    r = await db.execute(
        select(KbPageFusion)
        .where(KbPageFusion.document_id == document_id)
        .order_by(KbPageFusion.page)
    )
    items = [
        {
            "page": pf.page,
            "page_title": pf.page_title,
            "fused_text": pf.fused_text,
            "page_summary": pf.page_summary,
            "confidence": pf.confidence,
            "conflicts": pf.conflicts_json or [],
        }
        for pf in r.scalars().all()
    ]
    return ApiResponse(data={"items": items})


@router.post("/documents/profile")
async def api_generate_profile(
    payload: ProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """生成第5层文件画像（后台任务 kb_profile）。"""
    return await _enqueue_task(db, "kb_profile", payload.document_id, user.id)


@router.get("/documents/{document_id}/profile")
async def api_get_profile(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await get_document(db, document_id, user.id)
    result = await get_document_profile(db, document_id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Document profile not found")
    return ApiResponse(data=result)


@router.post("/documents/compute-relations")
async def api_compute_relations(
    payload: RelationComputeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """为文件计算跨文件关联边（第7层，后台任务 kb_relation）。"""
    return await _enqueue_task(db, "kb_relation", payload.document_id, user.id)


@router.get("/documents/{document_id}/relations")
async def api_get_relations(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await get_document(db, document_id, user.id)
    result = await get_file_relations(db, document_id)
    return ApiResponse(data={"relations": result})


@router.get("/relation-graph")
async def api_relation_graph(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """获取文档级知识网络全景图。"""
    result = await get_relation_graph(db, user.id)
    return ApiResponse(data=result)


@router.get("/entity-graph")
async def api_entity_graph(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """获取实体级知识图谱（节点=实体/概念/标签，边=关系）。"""
    from .models import KbGraphNode, KbGraphEdge
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


@router.post("/documents/rebuild-graph")
async def api_rebuild_graph(
    payload: ProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """从融合层重建实体/图谱（第6层，后台任务 kb_graph，防同步超时）。"""
    import json as _json
    from app.models.system import SystemTaskQueue

    await get_document(db, payload.document_id, user.id)

    task = SystemTaskQueue(
        task_type="kb_graph",
        module="knowledge",
        parameters=_json.dumps({"document_id": payload.document_id}, ensure_ascii=False),
        priority=5,
        status="pending",
        creator_id=user.id,
    )
    db.add(task)
    await db.commit()
    return ApiResponse(data={"task_id": task.id, "status": "enqueued"})


@router.post("/documents/full-pipeline")
async def api_full_pipeline(
    payload: ProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """一键全链路：采集→融合→画像→图谱→关联（后台任务 kb_pipeline）。"""
    import json as _json
    from app.models.system import SystemTaskQueue

    # 验证文档存在
    await get_document(db, payload.document_id, user.id)

    task = SystemTaskQueue(
        task_type="kb_pipeline",
        module="knowledge",
        parameters=_json.dumps({
            "document_id": payload.document_id,
            "user_id": user.id,
            "force_raw": payload.force_raw,
            "force_fusion": payload.force_fusion,
        }, ensure_ascii=False),
        priority=5,
        status="pending",
        creator_id=user.id,
    )
    db.add(task)
    await db.commit()
    return ApiResponse(data={"task_id": task.id, "status": "enqueued"})


@router.get("/documents/{document_id}/progress")
async def api_document_progress(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """单文档细颗粒分析进度(前端轮询/重开握手用)。"""
    result = await get_document_progress(db, document_id, user.id)
    return ApiResponse(data=result)


@router.post("/documents/progress-batch")
async def api_progress_batch(
    payload: ProgressBatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """批量查进度。前端打开/重开时一次握手所有处理中文档,实时同步后端真实进度。"""
    result = await list_documents_progress(db, user.id, payload.document_ids)
    return ApiResponse(data=result)


@router.get("/dashboard/stats")
async def api_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    from .models import (
        KbDocument, KbEntityDictionary, KbGraphNode, KbGraphEdge,
        KbFileRelation, KbGovernanceCandidate, KbDocumentProfile,
    )

    total = (await db.execute(
        select(func.count(KbDocument.id)).where(KbDocument.deleted == False, KbDocument.owner_id == user.id)
    )).scalar() or 0

    # 完成=权威口径: fusion done + 画像存在 (与 progress_service.get_document_progress 一致)
    completed = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted == False, KbDocument.owner_id == user.id,
            KbDocument.fusion_status == "done",
            exists(
                select(KbDocumentProfile.id).where(
                    KbDocumentProfile.document_id == KbDocument.id
                )
            ),
        )
    )).scalar() or 0

    failed = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted == False, KbDocument.owner_id == user.id,
            or_(KbDocument.raw_status == "failed", KbDocument.fusion_status == "failed"),
        )
    )).scalar() or 0

    pending = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted == False, KbDocument.owner_id == user.id,
            KbDocument.raw_status == "pending", KbDocument.fusion_status == "pending",
        )
    )).scalar() or 0

    running = total - completed - failed - pending

    entity_count = (await db.execute(
        select(func.count(KbEntityDictionary.id)).where(KbEntityDictionary.owner_id == user.id)
    )).scalar() or 0

    relation_count = (await db.execute(
        select(func.count(KbGraphEdge.id)).where(KbGraphEdge.owner_id == user.id)
    )).scalar() or 0

    file_relation_count = (await db.execute(
        select(func.count(KbFileRelation.id)).where(KbFileRelation.owner_id == user.id)
    )).scalar() or 0

    duplicate_entities = 0
    dup_rows = await db.execute(
        select(KbEntityDictionary.name, func.count(KbEntityDictionary.id))
        .where(KbEntityDictionary.owner_id == user.id, KbEntityDictionary.status != "merged")
        .group_by(KbEntityDictionary.name)
        .having(func.count(KbEntityDictionary.id) > 1)
    )
    dup_groups = dup_rows.all()
    duplicate_entities = sum(cnt for _, cnt in dup_groups)

    cat_rows = await db.execute(
        select(KbEntityDictionary.category, func.count(KbEntityDictionary.id))
        .where(KbEntityDictionary.owner_id == user.id)
        .group_by(KbEntityDictionary.category)
        .order_by(func.count(KbEntityDictionary.id).desc())
    )
    entity_category_distribution = {cat: cnt for cat, cnt in cat_rows.all()}

    all_docs = await db.execute(
        select(KbDocument).where(KbDocument.deleted == False, KbDocument.owner_id == user.id)
        .order_by(KbDocument.id.desc())
    )
    doc_progresses = []
    stuck_docs = []
    for d in all_docs.scalars().all():
        entry = {
            "id": d.id, "filename": d.filename, "total_pages": d.total_pages,
            "raw_status": d.raw_status, "fusion_status": d.fusion_status,
            "parse_status": d.parse_status, "created_at": str(d.created_at or ""),
        }
        doc_progresses.append(entry)
        if d.raw_status == "failed" or d.fusion_status == "failed":
            stuck_docs.append(entry)

    # 最近完成也用权威口径: fusion done + 画像存在
    recent = (await db.execute(
        select(KbDocument).where(
            KbDocument.deleted == False, KbDocument.owner_id == user.id,
            KbDocument.fusion_status == "done",
            exists(
                select(KbDocumentProfile.id).where(
                    KbDocumentProfile.document_id == KbDocument.id
                )
            ),
        )
        .order_by(KbDocument.updated_at.desc().nullslast())
        .limit(10)
    )).scalars().all()
    recent_completions = [
        {"id": d.id, "filename": d.filename, "completed_at": str(d.updated_at or "")}
        for d in recent
    ]

    return ApiResponse(data={
        "total_documents": total,
        "completed_documents": completed,
        "running_documents": running,
        "failed_documents": failed,
        "total_entities": entity_count,
        "total_graph_relations": relation_count,
        "total_file_relations": file_relation_count,
        "duplicate_entity_count": duplicate_entities,
        "duplicate_entity_groups": [{"name": name, "count": cnt} for name, cnt in dup_groups],
        "entity_category_distribution": entity_category_distribution,
        "document_progresses": doc_progresses,
        "stuck_documents": stuck_docs,
        "recent_completions": recent_completions,
    })

@router.post("/search")
async def api_search(
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await hybrid_search(db, payload.query, user.id, payload.top_k, payload.use_rerank)
    return ApiResponse(data={"query": payload.query, "results": result})


@router.get("/documents/{document_id}/chunks")
async def api_document_chunks(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    # 文档归属检查
    await get_document(db, document_id, user.id)
    result = await get_document_chunks(db, document_id)
    return ApiResponse(data=result)


@router.get("/chunks/{chunk_id}")
async def api_get_chunk(
    chunk_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await get_chunk_by_id(db, chunk_id)
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Chunk not found")
    # owner 隔离：chunk.owner_id 校验由服务 payload 不含 owner，重新查一次保护
    if result["document_id"]:
        await get_document(db, result["document_id"], user.id)
    return ApiResponse(data=result)


@router.get("/documents/{document_id}/page/{page}")
async def api_get_page_fusion(
    document_id: int,
    page: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await get_document(db, document_id, user.id)
    result = await get_page_fusion(db, document_id, page)
    return ApiResponse(data=result)


@router.get("/entities")
async def api_entities(
    keyword: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await get_entity_dictionary(db, user.id, keyword)
    return ApiResponse(data=result)


@router.get("/entities/{entity_id}/graph")
async def api_graph_context(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await get_graph_context(db, user.id, entity_id)
    return ApiResponse(data=result)


@router.get("/entities/{entity_id}/evidence")
async def api_evidence_detail(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await get_evidence_detail(db, user.id, entity_id)
    return ApiResponse(data=result)


@router.get("/governance/candidates")
async def api_governance_candidates(
    audit_status: str = Query(default="pending"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    result = await list_governance_candidates(db, user.id, audit_status, page, page_size)
    return ApiResponse(data=result)


@router.post("/governance/candidates/{candidate_id}/approve")
async def api_approve_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    ok = await approve_candidate(db, candidate_id, user.id)
    return ApiResponse(data={"ok": ok})


@router.post("/governance/candidates/{candidate_id}/reject")
async def api_reject_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    ok = await reject_candidate(db, candidate_id, user.id)
    return ApiResponse(data={"ok": ok})


@router.post("/governance/entities/merge")
async def api_merge_entities(
    payload: MergeEntitiesRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    ok = await merge_entities(db, payload.source_entity_ids, payload.target_entity_id, user.id, payload.reason)
    return ApiResponse(data={"ok": ok})


@router.post("/governance/calibrate")
async def api_calibrate(
    payload: CalibrateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    ok = await calibrate_extraction(db, payload.candidate_id, payload.new_name, payload.new_category, user.id)
    return ApiResponse(data={"ok": ok})


@router.get("/governance/pending-count")
async def api_pending_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await get_pending_count(db, user.id)
    return ApiResponse(data={"pending_count": result})


# ── Cross-module capabilities ───────────────────────────────


async def _enqueue_task(db, task_type: str, document_id: int, user_id: int) -> ApiResponse:
    """将派生层任务入队并立即返回。"""
    import json as _json
    from app.models.system import SystemTaskQueue
    from .models import KbDocument

    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == user_id,
            KbDocument.deleted == False,
        )
    )
    if not r.scalar_one_or_none():
        from app.core.exceptions import NotFound
        raise NotFound("Document not found")

    task = SystemTaskQueue(
        task_type=task_type,
        module="knowledge",
        parameters=_json.dumps({"document_id": document_id}, ensure_ascii=False),
        priority=5,
        status="pending",
        creator_id=user_id,
    )
    db.add(task)
    await db.commit()
    return ApiResponse(data={"task_id": task.id, "status": "enqueued"})


# ── Cross-module capabilities ───────────────────────────────


async def _cap_search(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    query = str(params.get("query", "")).strip()
    top_k = int(params.get("top_k", 10) or 10)
    if not query:
        raise ValueError("query is required")
    async with AsyncSessionLocal() as db:
        results = await hybrid_search(db, query, owner_id, top_k=top_k, use_rerank=False)
        # 为每个结果补充页级融合内容和文档名称
        from .entity_service import get_page_fusion as _get_page_fusion
        from .models import KbDocument
        enriched = []
        doc_cache: dict[int, str] = {}
        for r in results:
            doc_id = r.get("document_id")
            page = r.get("page")
            if doc_id and page:
                fusion = await _get_page_fusion(db, doc_id, page)
                r["page_fusion"] = fusion
            if doc_id and doc_id not in doc_cache:
                dr = await db.execute(select(KbDocument).where(KbDocument.id == doc_id, KbDocument.owner_id == owner_id))
                doc = dr.scalar_one_or_none()
                doc_cache[doc_id] = doc.filename if doc else ""
            r["document_name"] = doc_cache.get(doc_id, "")
            enriched.append(r)
        return {"query": query, "results": enriched}


async def _cap_get_block(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    block_id = int(params.get("block_id", 0) or 0)
    if block_id <= 0:
        raise ValueError("block_id must be positive")
    async with AsyncSessionLocal() as db:
        result = await get_chunk_by_id(db, block_id)
        if not result:
            return {"block": None}
        await get_document(db, result["document_id"], owner_id)
        return {"block": result}


async def _cap_get_page_fusion(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    document_id = int(params.get("document_id", 0) or 0)
    page = int(params.get("page", 1) or 1)
    async with AsyncSessionLocal() as db:
        await get_document(db, document_id, owner_id)
        result = await get_page_fusion(db, document_id, page)
        return {"page_fusion": result}


async def _cap_get_entity_dictionary(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    keyword = str(params.get("keyword", "") or "")
    async with AsyncSessionLocal() as db:
        result = await get_entity_dictionary(db, owner_id, keyword)
        return {"entities": result}


async def _cap_get_graph_context(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    entity_id = int(params.get("entity_id", 0) or 0)
    async with AsyncSessionLocal() as db:
        result = await get_graph_context(db, owner_id, entity_id)
        return {"graph": result}


async def _cap_get_pending_count(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        count = await get_pending_count(db, owner_id)
        return {"pending_count": count}


async def _cap_get_evidence_detail(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    entity_id = int(params.get("entity_id", 0) or 0)
    async with AsyncSessionLocal() as db:
        result = await get_evidence_detail(db, owner_id, entity_id)
        return {"evidence": result}


# 注册对外能力：Agent 会通过 list_capabilities 自动发现 knowledge__search 等工具。
register_capability(
    "knowledge", "search", _cap_search,
    description="Search enterprise knowledge base and return relevant text chunks with source metadata",
    parameters={
        "query": {"type": "string", "description": "Search query"},
        "top_k": {"type": "integer", "description": "Number of results, default 5"},
    },
    min_role="viewer",
)
register_capability(
    "knowledge", "get_block", _cap_get_block,
    description="Get a knowledge base content block by block_id",
    parameters={"block_id": {"type": "integer", "description": "Content block ID"}},
    min_role="viewer",
)
register_capability(
    "knowledge", "get_page_fusion", _cap_get_page_fusion,
    description="Get fused page-level content for a document page",
    parameters={
        "document_id": {"type": "integer", "description": "Document ID"},
        "page": {"type": "integer", "description": "Page number"},
    },
    min_role="viewer",
)
register_capability(
    "knowledge", "get_entity_dictionary", _cap_get_entity_dictionary,
    description="Query the knowledge base entity dictionary",
    parameters={"keyword": {"type": "string", "description": "Optional keyword"}},
    min_role="viewer",
)
register_capability(
    "knowledge", "get_graph_context", _cap_get_graph_context,
    description="Get graph context around an entity",
    parameters={"entity_id": {"type": "integer", "description": "Entity ID"}},
    min_role="viewer",
)
register_capability(
    "knowledge", "get_pending_count", _cap_get_pending_count,
    description="Get pending governance candidate count",
    parameters={},
    min_role="viewer",
)
register_capability(
    "knowledge", "get_evidence_detail", _cap_get_evidence_detail,
    description="Get evidence details for an entity",
    parameters={"entity_id": {"type": "integer", "description": "Entity ID"}},
    min_role="viewer",
)

# ── 入库能力（供上传桥接用，对外暴露，编辑以上角色可调） ──

INGEST_EXTENSIONS = {
    "pdf", "docx", "pptx", "xlsx", "csv", "txt", "md",
    "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg",
}


async def _cap_ingest(params: dict, caller: str) -> dict:
    """把已上传文件登记进知识库并触发后台分析（幂等、类型白名单）。"""
    from .document_service import register_document
    from .models import KbDocument
    from app.models.file import File

    owner_id = resolve_user_id(caller)
    file_id = int(params.get("file_id", 0) or 0)
    if file_id <= 0:
        return {"skipped": True, "reason": "invalid file_id"}

    async with AsyncSessionLocal() as db:
        # 类型白名单判断：先查文件扩展名
        fr = await db.execute(select(File).where(File.id == file_id))
        file = fr.scalar_one_or_none()
        if not file:
            return {"skipped": True, "reason": "file not found"}
        ext = (file.extension or "").lower().strip(".")
        if ext not in INGEST_EXTENSIONS:
            logger.info("ingest skipped: unsupported extension '%s' for file_id=%d", ext, file_id)
            return {"skipped": True, "reason": f"unsupported extension '{ext}'"}

        # 已存在则返回现有记录
        existing_r = await db.execute(
            select(KbDocument).where(
                KbDocument.file_id == file_id,
                KbDocument.owner_id == owner_id,
                KbDocument.deleted == False,
            )
        )
        existing = existing_r.scalar_one_or_none()
        if existing:
            return {"document_id": existing.id, "enqueued": False, "reason": "already registered"}

        # register_document 幂等且自动入队 kb_pipeline
        result = await register_document(db, file_id, owner_id, catalog_id=None)
        return {"document_id": result["id"], "enqueued": True}


register_capability(
    "knowledge", "ingest", _cap_ingest,
    description="把已上传文件登记进知识库并触发后台分析（幂等、类型白名单）",
    parameters={"file_id": {"type": "integer", "description": "Uploaded file ID"}},
    min_role="editor",
)
