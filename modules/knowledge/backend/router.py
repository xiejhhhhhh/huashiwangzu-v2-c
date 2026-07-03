"""FastAPI router for knowledge module.

业务接口全部在模块内；对外能力通过框架 register_capability 注册，供 Agent 自动发现和调用。
"""
import logging
from typing import Literal

from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_events import register_module_event_handler
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .init_db import _run_startup_init
from .services import file_lifecycle_service, pipeline_service  # noqa: F401
from .services.dashboard_service import get_dashboard_stats
from .services.document_service import (
    enqueue_pipeline_task,
    get_document,
    list_documents,
    parse_and_index_document,
    register_document,
    resolve_user_id,
    soft_delete_document,
)
from .services.embedding_service import get_chunk_by_id
from .services.entity_service import get_entity_dictionary, get_graph_context, get_page_fusion
from .services.fusion_service import get_page_fusion_detail
from .services.governance_service import (
    approve_candidate,
    calibrate_extraction,
    get_evidence_detail,
    get_pending_count,
    list_governance_candidates,
    merge_entities,
    reject_candidate,
)
from .services.ingest_status_service import get_ingest_status
from .services.pipeline_debt_service import (
    apply_pipeline_lifecycle_debt_action,
    classify_pipeline_lifecycle_debt,
)
from .services.pipeline_reconcile_service import (
    apply_orphan_pipeline_run_reconcile,
    dry_run_orphan_pipeline_run_reconcile,
)
from .services.profile_service import get_document_profile
from .services.progress_service import get_document_progress, list_documents_progress
from .services.raw_collection_service import get_ocr_words, get_raw_data
from .services.relation_service import get_file_relations, get_relation_graph
from .services.search_service import get_document_chunks, hybrid_search
from .services.source_file_state import get_live_document_or_raise

logger = logging.getLogger("v2.knowledge").getChild("router")
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
class PipelineDebtApplyRequest(BaseModel):
    action: Literal["archive_obsolete", "retry_live"]
    limit: int = Field(default=500, ge=1, le=5000)
    task_ids: list[int] = Field(default_factory=list)
    dry_run: bool = True
class PipelineRunReconcileRequest(BaseModel):
    limit: int = Field(default=500, ge=1, le=5000)
    run_ids: list[int] = Field(default_factory=list)
    dry_run: bool = True

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
    import json as _json

    from app.models.system import SystemTaskQueue

    from .models import KbDocument

    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == payload.document_id,
            KbDocument.owner_id == user.id,
            KbDocument.deleted.is_(False),
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
    await get_live_document_or_raise(db, document_id, user.id)
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
    await get_live_document_or_raise(db, document_id, user.id)
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
    await get_live_document_or_raise(db, document_id, user.id)
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
    await get_live_document_or_raise(db, document_id, user.id)
    result = await get_document_profile(db, document_id, owner_id=user.id)
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
    from .models import KbGraphEdge, KbGraphNode
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
    from app.core.exceptions import NotFound

    from .models import KbDocument

    # 验证文档存在
    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == payload.document_id,
            KbDocument.owner_id == user.id,
            KbDocument.deleted.is_(False),
        )
    )
    doc = r.scalar_one_or_none()
    if not doc:
        raise NotFound("Document not found")

    task_info = await enqueue_pipeline_task(
        db,
        doc,
        user.id,
        force_raw=payload.force_raw,
        force_fusion=payload.force_fusion,
    )
    await db.commit()
    status = "enqueued" if task_info.get("enqueued") else "already_in_flight"
    return ApiResponse(data={"status": status, **task_info})

@router.get("/documents/{document_id}/progress")
async def api_document_progress(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """单文档细颗粒分析进度(前端轮询/重开握手用)。"""
    result = await get_document_progress(db, document_id, user.id)
    return ApiResponse(data=result)

@router.get("/documents/{document_id}/ingest-status")
async def api_document_ingest_status(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """Unified ingest queue + document stage status for Agent/frontend polling."""
    result = await get_ingest_status(db, document_id, user.id)
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
    user: User = Depends(require_permission("viewer")),
):
    """知识库看板统计。"""
    result = await get_dashboard_stats(db, user.id)
    return ApiResponse(data=result)

@router.post("/search")
async def api_search(
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    results = await hybrid_search(db, payload.query, user.id, payload.top_k, payload.use_rerank)
    # Enrich with content_package_id and block_id
    from .models import KbChunk, KbDocument
    enriched = []
    doc_cache: dict[int, dict] = {}
    for r in results:
        doc_id = r.get("document_id")
        chunk_id = r.get("chunk_id")
        if doc_id and doc_id not in doc_cache:
            dr = await db.execute(select(KbDocument).where(KbDocument.id == doc_id, KbDocument.owner_id == user.id))
            doc = dr.scalar_one_or_none()
            doc_cache[doc_id] = {
                "name": doc.filename if doc else "",
                "content_package_id": doc.content_package_id if doc and hasattr(doc, "content_package_id") else None,
            }
        doc_info = doc_cache.get(doc_id, {})
        r["document_name"] = doc_info.get("name", "")
        r["content_package_id"] = doc_info.get("content_package_id")
        if chunk_id:
            cr = await db.execute(
                select(KbChunk.block_id).where(KbChunk.id == chunk_id, KbChunk.owner_id == user.id)
            )
            r["block_id"] = cr.scalar_one_or_none()
        else:
            r["block_id"] = None
        enriched.append(r)
    return ApiResponse(data={"query": payload.query, "results": enriched})

@router.get("/documents/{document_id}/chunks")
async def api_document_chunks(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await get_live_document_or_raise(db, document_id, user.id)
    result = await get_document_chunks(db, document_id, owner_id=user.id)
    return ApiResponse(data=result)

@router.get("/chunks/{chunk_id}")
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

@router.get("/documents/{document_id}/page/{page}")
async def api_get_page_fusion(
    document_id: int,
    page: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await get_live_document_or_raise(db, document_id, user.id)
    result = await get_page_fusion(db, document_id, page, owner_id=user.id)
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

@router.get("/governance/pipeline-debt/dry-run")
async def api_pipeline_debt_dry_run(
    limit: int = Query(default=500, ge=1, le=5000),
    error_marker: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    result = await classify_pipeline_lifecycle_debt(db, limit=limit, error_marker=error_marker)
    return ApiResponse(data=result)

@router.post("/governance/pipeline-debt/apply")
async def api_pipeline_debt_apply(
    payload: PipelineDebtApplyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    result = await apply_pipeline_lifecycle_debt_action(
        db,
        action=payload.action,
        limit=payload.limit,
        task_ids=payload.task_ids or None,
        dry_run=payload.dry_run,
    )
    return ApiResponse(data=result)

@router.get("/governance/pipeline-runs/orphan-running/dry-run")
async def api_orphan_pipeline_run_reconcile_dry_run(
    limit: int = Query(default=500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    _ = user
    result = await dry_run_orphan_pipeline_run_reconcile(db, limit=limit)
    return ApiResponse(data=result)

@router.post("/governance/pipeline-runs/orphan-running/apply")
async def api_orphan_pipeline_run_reconcile_apply(
    payload: PipelineRunReconcileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin")),
):
    _ = user
    result = await apply_orphan_pipeline_run_reconcile(
        db,
        limit=payload.limit,
        run_ids=payload.run_ids or None,
        dry_run=payload.dry_run,
    )
    return ApiResponse(data=result)

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
            KbDocument.deleted.is_(False),
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

async def _cap_search(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    query = str(params.get("query", "")).strip()
    top_k = int(params.get("top_k", 10) or 10)
    if not query:
        raise ValueError("query is required")
    async with AsyncSessionLocal() as db:
        results = await hybrid_search(db, query, owner_id, top_k=top_k, use_rerank=False)
        # 为每个结果补充页级融合内容和文档名称
        from .models import KbChunk, KbDocument
        from .services.entity_service import get_page_fusion as _get_page_fusion
        enriched = []
        doc_cache: dict[int, dict] = {}
        for r in results:
            doc_id = r.get("document_id")
            page = r.get("page")
            chunk_id = r.get("chunk_id")
            if doc_id and page:
                fusion = await _get_page_fusion(db, doc_id, page, owner_id=owner_id)
                r["page_fusion"] = fusion
            if doc_id and doc_id not in doc_cache:
                dr = await db.execute(select(KbDocument).where(KbDocument.id == doc_id, KbDocument.owner_id == owner_id))
                doc = dr.scalar_one_or_none()
                doc_cache[doc_id] = {
                    "name": doc.filename if doc else "",
                    "content_package_id": doc.content_package_id if doc and hasattr(doc, "content_package_id") else None,
                }
            doc_info = doc_cache.get(doc_id, {})
            r["document_name"] = doc_info.get("name", "")
            r["content_package_id"] = doc_info.get("content_package_id")
            # Look up block_id from chunk
            if chunk_id:
                cr = await db.execute(
                    select(KbChunk.block_id).where(KbChunk.id == chunk_id, KbChunk.owner_id == owner_id)
                )
                r["block_id"] = cr.scalar_one_or_none()
            else:
                r["block_id"] = None
            enriched.append(r)
        return {"query": query, "results": enriched}

async def _cap_get_block(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    block_id = int(params.get("block_id", 0) or 0)
    if block_id <= 0:
        raise ValueError("block_id must be positive")
    async with AsyncSessionLocal() as db:
        result = await get_chunk_by_id(db, block_id, owner_id=owner_id)
        if not result:
            return {"block": None}
        return {"block": result}

async def _cap_get_page_fusion(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    document_id = int(params.get("document_id", 0) or 0)
    page = int(params.get("page", 1) or 1)
    async with AsyncSessionLocal() as db:
        await get_live_document_or_raise(db, document_id, owner_id)
        result = await get_page_fusion(db, document_id, page, owner_id=owner_id)
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

async def _cap_classify_pipeline_debt(params: dict, caller: str) -> dict:
    resolve_user_id(caller)
    limit = int(params.get("limit", 500) or 500)
    limit = max(1, min(limit, 5000))
    async with AsyncSessionLocal() as db:
        return await classify_pipeline_lifecycle_debt(db, limit=limit)

async def _cap_reconcile_orphan_pipeline_runs(params: dict, caller: str) -> dict:
    resolve_user_id(caller)
    limit = int(params.get("limit", 500) or 500)
    limit = max(1, min(limit, 5000))
    raw_run_ids = params.get("run_ids") or []
    run_ids = [int(run_id) for run_id in raw_run_ids] if isinstance(raw_run_ids, list) else []
    dry_run = bool(params.get("dry_run", True))
    async with AsyncSessionLocal() as db:
        return await apply_orphan_pipeline_run_reconcile(
            db,
            limit=limit,
            run_ids=run_ids or None,
            dry_run=dry_run,
        )

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
    brief="检索知识库",
    parameters={
        "query": {"type": "string", "description": "Search query"},
        "top_k": {"type": "integer", "description": "Number of results, default 5"},
    },
    min_role="viewer",
)
register_capability(
    "knowledge", "get_block", _cap_get_block,
    description="Get a knowledge base content block by block_id",
    brief="获取知识块详情",
    parameters={"block_id": {"type": "integer", "description": "Content block ID"}},
    min_role="viewer",
)
register_capability(
    "knowledge", "get_page_fusion", _cap_get_page_fusion,
    description="Get fused page-level content for a document page",
    brief="获取页面融合内容",
    parameters={
        "document_id": {"type": "integer", "description": "Document ID"},
        "page": {"type": "integer", "description": "Page number"},
    },
    min_role="viewer",
)
register_capability(
    "knowledge", "get_entity_dictionary", _cap_get_entity_dictionary,
    description="Query the knowledge base entity dictionary",
    brief="查询实体词典",
    parameters={"keyword": {"type": "string", "description": "Optional keyword"}},
    min_role="viewer",
)
register_capability(
    "knowledge", "get_graph_context", _cap_get_graph_context,
    description="Get graph context around an entity",
    brief="查询实体图谱",
    parameters={"entity_id": {"type": "integer", "description": "Entity ID"}},
    min_role="viewer",
)
register_capability(
    "knowledge", "get_pending_count", _cap_get_pending_count,
    description="Get pending governance candidate count",
    brief="待治理数量",
    parameters={},
    min_role="viewer",
)
register_capability(
    "knowledge", "classify_pipeline_debt", _cap_classify_pipeline_debt,
    description="Dry-run classify historical knowledge pipeline debt without mutating queue rows",
    brief="分类知识库管道债",
    parameters={
        "limit": {"type": "integer", "description": "Maximum failed tasks to inspect, default 500"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "reconcile_orphan_pipeline_runs", _cap_reconcile_orphan_pipeline_runs,
    description="Dry-run or apply guarded reconcile for orphan running kb_pipeline_runs with no queue task",
    brief="收口孤儿管道运行",
    parameters={
        "limit": {"type": "integer", "description": "Maximum orphan runs to inspect, default 500"},
        "run_ids": {"type": "array", "description": "Optional run IDs to restrict apply/dry-run"},
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "get_evidence_detail", _cap_get_evidence_detail,
    description="Get evidence details for an entity",
    brief="查看治理证据",
    parameters={"entity_id": {"type": "integer", "description": "Entity ID"}},
    min_role="viewer",
)

async def _cap_get_ocr_words(params: dict, caller: str) -> dict:
    """返回 PDF 某页 OCR 词坐标（供 pdf-viewer 叠文字层）。"""
    owner_id = resolve_user_id(caller)
    file_id = int(params.get("file_id", 0) or 0)
    page = int(params.get("page", 1) or 1)
    if file_id <= 0:
        return {"words": [], "img_w": 0, "img_h": 0}
    async with AsyncSessionLocal() as db:
        result = await get_ocr_words(db, file_id, page, owner_id)
        return result

register_capability(
    "knowledge", "get_ocr_words", _cap_get_ocr_words,
    description="Get OCR word coordinates for a PDF page (for text layer overlay)",
    brief="获取PDF页OCR词坐标",
    parameters={
        "file_id": {"type": "integer", "description": "File ID"},
        "page": {"type": "integer", "description": "Page number (1-based)"},
    },
    min_role="viewer",
)

# ── 入库能力（供上传桥接用，对外暴露，编辑以上角色可调） ──

INGEST_EXTENSIONS = {
    "pdf", "docx", "pptx", "xlsx", "csv", "txt", "md",
    "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg",
}

async def _cap_ingest(params: dict, caller: str) -> dict:
    """把已上传文件登记进知识库并触发后台分析（幂等、类型白名单）。"""
    from .services.document_service import register_document

    owner_id = resolve_user_id(caller)
    file_id = int(params.get("file_id", 0) or 0)
    if file_id <= 0:
        return {"skipped": True, "reason": "invalid file_id"}

    async with AsyncSessionLocal() as db:
        # 权限校验：验证当前用户有该文件的访问权限
        from app.core.exceptions import NotFound, PermissionDenied
        from app.services.file_service import check_file_access
        try:
            file = await check_file_access(db, file_id, owner_id)
        except (NotFound, PermissionDenied):
            return {"skipped": True, "reason": "file not found or access denied"}
        ext = (file.extension or "").lower().strip(".")
        if ext not in INGEST_EXTENSIONS:
            logger.info("ingest skipped: unsupported extension '%s' for file_id=%d", ext, file_id)
            return {"skipped": True, "reason": f"unsupported extension '{ext}'"}

        # register_document 幂等且自动入队 kb_pipeline
        result = await register_document(db, file_id, owner_id, catalog_id=None)
        status = await get_ingest_status(db, int(result["id"]), owner_id)
        response = {**status, **result, "document_id": int(result["id"])}
        response["status"] = status["status"]
        response["pipeline_status"] = status["pipeline_status"]
        response["stage"] = status["stage"]
        response["stage_summary"] = status["stage_summary"]
        response["search_ready"] = status["search_ready"]
        response["deep_ready"] = status["deep_ready"]
        return response

# ── Chunking strategy support ──────────────────────────────────────

class ChunkRequest(BaseModel):
    document_id: int
    strategy: str = "title_aware"  # title_aware / structure_aware / fixed_size
    max_chars: int = 512


@router.post("/documents/chunk")
async def api_chunk_document(
    payload: ChunkRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """Re-chunk a parsed document using the specified strategy (title_aware/structure_aware/fixed_size)."""
    await get_live_document_or_raise(db, payload.document_id, user.id)
    from sqlalchemy import delete as sa_delete

    from ..ir_models import from_legacy_blocks
    from ..models import KbChunk, KbDocument
    from .services.chunking_service import chunk_document
    from .services.search_service import get_document_chunks

    # Read existing chunks as DocumentIr
    current_chunks = await get_document_chunks(db, payload.document_id, owner_id=user.id)
    ir_blocks = []
    for ch in current_chunks:
        bt = ch.get("block_type", "段落")
        if bt in ("标题",):
            block_type = "heading"
        else:
            block_type = "paragraph"
        ir_blocks.append({"type": block_type, "text": ch.get("text", ""), "page": ch.get("page")})

    if not ir_blocks:
        return ApiResponse(data={"error": "No chunks to re-chunk", "chunks": 0})

    doc_ir = from_legacy_blocks(file_id=0, fmt="", blocks=ir_blocks)

    # Delete old chunks and store new ones
    await db.execute(sa_delete(KbChunk).where(KbChunk.document_id == payload.document_id))
    await db.commit()

    new_chunks = chunk_document(doc_ir, strategy=payload.strategy, max_chars=payload.max_chars)
    stored = 0
    for i, ch in enumerate(new_chunks):
        record = KbChunk(
            document_id=payload.document_id,
            owner_id=user.id,
            page=ch.get("page"),
            chunk_index=i,
            block_type=ch.get("block_type", "段落"),
            text=ch.get("text", ""),
            keywords="",
        )
        db.add(record)
        stored += 1
        if stored % 50 == 0:
            await db.flush()
    await db.commit()

    dr = await db.execute(select(KbDocument).where(KbDocument.id == payload.document_id))
    doc = dr.scalar_one_or_none()
    if doc:
        doc.total_chunks = stored

    await db.commit()
    return ApiResponse(data={"chunks": stored, "strategy": payload.strategy})


# ── Export endpoint ────────────────────────────────────────────────

class ExportRequest(BaseModel):
    document_id: int
    format: str = "markdown"  # markdown / html / json


@router.post("/documents/export")
async def api_export_document(
    payload: ExportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """Export a parsed document in markdown/html/json format."""
    from .services.export_service import export_document

    await get_live_document_or_raise(db, payload.document_id, user.id)
    result = await export_document(db, payload.document_id, fmt=payload.format, owner_id=user.id)
    if not result.get("success"):
        from app.core.exceptions import NotFound, ValidationError
        if result.get("error", "").startswith("Document not"):
            raise NotFound(result["error"])
        raise ValidationError(result.get("error", "Export failed"))
    return ApiResponse(data=result)
# ── Capability registrations ──────────────────────────────────────
register_capability(
    "knowledge", "ingest", _cap_ingest,
    description="把已上传文件登记进知识库并触发后台分析（幂等、类型白名单）",
    brief="文件入库知识库",
    parameters={"file_id": {"type": "integer", "description": "Uploaded file ID"}},
    min_role="editor",
)

async def _cap_get_ingest_status(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    document_id = int(params.get("document_id", 0) or 0)
    if document_id <= 0:
        raise ValueError("document_id must be positive")
    async with AsyncSessionLocal() as db:
        return await get_ingest_status(db, document_id, owner_id)

register_capability(
    "knowledge", "get_ingest_status", _cap_get_ingest_status,
    description="Get unified knowledge ingest status for a document, including queue task and stage readiness",
    brief="查询入库状态",
    parameters={"document_id": {"type": "integer", "description": "Document ID"}},
    min_role="viewer",
)
async def _cap_export(params: dict, caller: str) -> dict:
    from app.database import AsyncSessionLocal

    from .services.export_service import export_document

    document_id = int(params.get("document_id", 0))
    fmt = params.get("format", "markdown")
    if document_id <= 0:
        return {"error": "document_id is required"}

    owner_id = None
    if caller.startswith("user:"):
        owner_id = int(caller.split(":", 1)[1])

    async with AsyncSessionLocal() as db:
        if owner_id is not None:
            await get_live_document_or_raise(db, document_id, owner_id)
        result = await export_document(db, document_id, fmt=fmt, owner_id=owner_id)
        return result
register_capability(
    "knowledge", "export", _cap_export,
    description="导出已解析文档（markdown/html/json）",
    brief="导出文档",
    parameters={"document_id": {"type": "integer"}, "format": {"type": "string"}},
    min_role="viewer",
)
async def _on_file_uploaded(payload: dict, caller: str, caller_role: str) -> dict:
    """Handle file.uploaded event: register file into knowledge base.

    Reuses _cap_ingest logic (type whitelist, idempotent, permission check).
    This is best-effort: failures are logged but do not block the upload flow.
    """
    return await _cap_ingest(payload, caller)
register_module_event_handler("file.uploaded", _on_file_uploaded, "knowledge")
