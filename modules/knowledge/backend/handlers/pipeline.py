"""Pipeline-related endpoints (collect-raw, fuse, profile, graph, relations, progress)."""
import logging
from typing import Literal

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services import pipeline_service
from ..services.chunk_rebuild_service import rebuild_document_chunks
from ..services.dashboard_service import get_dashboard_stats
from ..services.document_service import enqueue_pipeline_task, get_document
from ..services.entity_service import get_page_fusion
from ..services.fusion_service import get_page_fusion_detail
from ..services.profile_service import get_document_profile
from ..services.progress_service import get_document_progress, list_documents_progress
from ..services.raw_collection_service import get_raw_data
from ..services.relation_service import get_file_relations, get_relation_graph
from ..services.source_file_state import get_live_document_or_raise

logger = logging.getLogger("v2.knowledge").getChild("handlers.pipeline")

sub_router = APIRouter()


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


class ChunkRequest(BaseModel):
    document_id: int
    strategy: str = "title_aware"  # title_aware / structure_aware / fixed_size
    max_chars: int = 512


async def _enqueue_task(db, stage: str, document_id: int, user_id: int) -> ApiResponse:
    """将统一 DAG stage 入队并立即返回。"""
    from ..models import KbDocument

    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == user_id,
            KbDocument.deleted.is_(False),
        )
    )
    doc = r.scalar_one_or_none()
    if not doc:
        from app.core.exceptions import NotFound
        raise NotFound("Document not found")

    task_info = await pipeline_service.enqueue_pipeline_stage_task(
        db,
        doc,
        user_id,
        stage,
    )
    await db.commit()
    status = "enqueued" if task_info.get("enqueued") else "already_in_flight"
    return ApiResponse(data={"status": status, **task_info})


@sub_router.post("/documents/collect-raw")
async def api_collect_raw(
    payload: CollectRawRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """触发统一 DAG pipeline（后台任务）。"""
    from ..models import KbDocument

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

    task_info = await enqueue_pipeline_task(
        db,
        doc,
        user.id,
        force_raw=True,
        priority=8,
    )
    await db.commit()
    status = "enqueued" if task_info.get("enqueued") else "already_in_flight"
    return ApiResponse(data={"status": status, **task_info})


@sub_router.get("/documents/{document_id}/raw-status")
async def api_raw_status(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    doc = await get_document(db, document_id, user.id)
    return ApiResponse(data={"document_id": document_id, "raw_status": doc.get("raw_status", doc.get("parse_status"))})


@sub_router.get("/documents/{document_id}/raw-data")
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


@sub_router.post("/documents/fuse")
async def api_fuse(
    payload: FuseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """触发页级融合（第4层，统一 DAG stage）。"""
    return await _enqueue_task(db, "fusion", payload.document_id, user.id)


@sub_router.get("/documents/{document_id}/fusion-status")
async def api_fusion_status(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    doc = await get_document(db, document_id, user.id)
    return ApiResponse(data={"document_id": document_id, "fusion_status": doc.get("fusion_status", "pending")})


@sub_router.get("/documents/{document_id}/page-fusion/{page}")
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


@sub_router.get("/documents/{document_id}/fusions")
async def api_list_fusions(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """列出文档所有页的融合内容(第4层,阅读视图用)。"""
    from ..models import KbPageFusion
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


@sub_router.post("/documents/profile")
async def api_generate_profile(
    payload: ProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """生成第5层文件画像（统一 DAG stage）。"""
    return await _enqueue_task(db, "profile", payload.document_id, user.id)


@sub_router.get("/documents/{document_id}/profile")
async def api_get_profile(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    doc = await get_live_document_or_raise(db, document_id, user.id)
    result = await get_document_profile(db, document_id, owner_id=int(doc["owner_id"]))
    if not result:
        from app.core.exceptions import NotFound
        raise NotFound("Document profile not found")
    return ApiResponse(data=result)


@sub_router.post("/documents/compute-relations")
async def api_compute_relations(
    payload: RelationComputeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """为文件计算跨文件关联边（统一 DAG stage）。"""
    return await _enqueue_task(db, "relations", payload.document_id, user.id)


@sub_router.get("/documents/{document_id}/relations")
async def api_get_relations(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    await get_document(db, document_id, user.id)
    result = await get_file_relations(db, document_id)
    return ApiResponse(data={"relations": result})


@sub_router.get("/relation-graph")
async def api_relation_graph(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """获取文档级知识网络全景图。"""
    result = await get_relation_graph(db, user.id)
    return ApiResponse(data=result)


@sub_router.post("/documents/rebuild-graph")
async def api_rebuild_graph(
    payload: ProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """从融合层重建实体/图谱（第6层，统一 DAG stage）。"""
    await get_document(db, payload.document_id, user.id)
    return await _enqueue_task(db, "graph", payload.document_id, user.id)


@sub_router.post("/documents/full-pipeline")
async def api_full_pipeline(
    payload: ProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """一键全链路：采集→融合→画像→图谱→关联（统一 DAG pipeline）。"""
    from app.core.exceptions import NotFound

    from ..models import KbDocument

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


@sub_router.get("/documents/{document_id}/progress")
async def api_document_progress(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """单文档细颗粒分析进度(前端轮询/重开握手用)。"""
    result = await get_document_progress(db, document_id, user.id)
    return ApiResponse(data=result)


@sub_router.post("/documents/progress-batch")
async def api_progress_batch(
    payload: ProgressBatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """批量查进度。前端打开/重开时一次握手所有处理中文档,实时同步后端真实进度。"""
    result = await list_documents_progress(db, user.id, payload.document_ids)
    return ApiResponse(data=result)


@sub_router.get("/dashboard/stats")
async def api_dashboard_stats(
    page: int = 1,
    page_size: int = 50,
    include_analytics: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """知识库看板统计。"""
    result = await get_dashboard_stats(
        db,
        user.id,
        page=max(1, page),
        page_size=max(10, min(page_size, 100)),
        include_analytics=include_analytics,
    )
    return ApiResponse(data=result)


@sub_router.post("/documents/chunk")
async def api_chunk_document(
    payload: ChunkRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """Re-chunk a parsed document using the specified strategy (title_aware/structure_aware/fixed_size)."""
    result = await rebuild_document_chunks(
        db,
        document_id=payload.document_id,
        owner_id=user.id,
        strategy=payload.strategy,
        max_chars=payload.max_chars,
    )
    return ApiResponse(data=result)
