"""FastAPI router for knowledge module.

业务接口全部在模块内；对外能力通过框架 register_capability 注册，供 Agent 自动发现和调用。
"""
import logging
from typing import Literal

from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.maintenance_service import ensure_accepting_new_work
from app.services.module_events import register_module_event_handler
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .init_db import _run_startup_init
from .services import file_lifecycle_service, pipeline_service  # noqa: F401
from .services.chunk_embedding_service import (
    DEFAULT_CHUNK_EMBEDDING_PROFILE,
    backfill_chunk_embeddings,
    enqueue_chunk_embedding_backfill_task,
    get_chunk_embedding_counts,
)
from .services.cognitive_index_service import (
    backfill_cognitive_index,
    derive_document_cognitive_index,
    persist_query_context,
)
from .services.derived_governance_service import (
    backfill_derived_governance,
    derived_governance_counts,
)
from .services.document_service import (
    enqueue_incomplete_documents,
    enqueue_pipeline_task,
    get_document,
    list_documents,
    list_documents_by_file_ids,
    parse_and_index_document,
    register_document,
    resolve_user_id,
    soft_delete_document,
)
from .services.embedding_service import get_chunk_by_id
from .services.enterprise_import_service import enqueue_enterprise_source_import, import_enterprise_source_batch

from .services.entity_service import get_entity_dictionary, get_graph_context, get_page_fusion
from .services.governance_service import (
    get_evidence_detail,
    get_pending_count,
)
from .services.ingest_status_service import get_ingest_status
from .services.lifecycle_debt_service import (
    archive_source_unavailable_documents,
    audit_lifecycle_debt,
)
from .services.pipeline_batch_service import enqueue_pipeline_stage_batch
from .services.pipeline_debt_api import (
    cap_apply_pipeline_debt,
    cap_classify_pipeline_debt,
    cap_reconcile_pending_pipeline_queue,
    cap_reconcile_running_pipeline_queue,
)
from .services.pipeline_debt_service import (
    apply_pipeline_lifecycle_debt_action,
    classify_pipeline_lifecycle_debt,
    reconcile_pending_pipeline_queue,
)
from .services.pipeline_reconcile_service import (
    apply_orphan_pipeline_run_reconcile,
    dry_run_orphan_pipeline_run_reconcile,
)
from .services.progress_service import get_document_progress, list_documents_progress
from .services.raw_collection_service import get_ocr_words
from .services.rerun_planner_service import plan_pipeline_rerun
from .services.retrieval_learning_service import reflect_retrieval_feedback
from .services.search_service import hybrid_search
from .services.source_file_state import get_live_document_or_raise
from .services.source_manifest_service import (
    enqueue_source_manifest_import,
    scan_source_manifest,
    source_manifest_summary,
)

logger = logging.getLogger("v2.knowledge").getChild("router")
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# ── 模块加载时初始化：建表 + 索引 + 列迁移（一次性，幂等） ──
_run_startup_init()

# ── Include sub-routers ──────────────────────────────────────────────
from .handlers.document import sub_router as document_router
from .handlers.embedding import sub_router as embedding_router
from .handlers.governance import sub_router as governance_router
from .handlers.pipeline import sub_router as pipeline_router
from .handlers.search import sub_router as search_router

router.include_router(document_router)
router.include_router(pipeline_router)
router.include_router(search_router)
router.include_router(governance_router)
router.include_router(embedding_router)


# ── Health endpoint (kept in main router) ────────────────────────────

@router.get("/health")
async def health():
    return ApiResponse(data={"module": "knowledge", "status": "ok"})


# ── Shared helper functions (used by sub-handlers via import) ────────

async def _enrich_search_results(
    db: AsyncSession,
    results: list[dict],
    owner_id: int,
    *,
    include_page_fusion: bool = False,
) -> tuple[list[dict], dict]:
    from app.models.file import File

    from .models import KbChunk, KbDocument
    from .services.entity_service import get_page_fusion as _get_page_fusion
    from .services.search_service import _accessible_document_clause

    enriched: list[dict] = []
    doc_cache: dict[int, dict] = {}
    chunk_cache: dict[int, dict] = {}
    file_ids: set[int] = set()
    document_ids: set[int] = set()

    for result in results:
        item = dict(result)
        doc_id = item.get("document_id")
        chunk_id = item.get("chunk_id")
        page = item.get("page")
        doc_info: dict = {}
        chunk_info: dict = {}

        if doc_id:
            document_ids.add(int(doc_id))
            if int(doc_id) not in doc_cache:
                dr = await db.execute(
                    select(KbDocument)
                    .join(File, File.id == KbDocument.file_id)
                    .where(
                        KbDocument.id == int(doc_id),
                        KbDocument.deleted.is_(False),
                        File.deleted.is_(False),
                        _accessible_document_clause(owner_id),
                    )
                )
                doc = dr.scalar_one_or_none()
                doc_cache[int(doc_id)] = {
                    "name": doc.filename if doc else "",
                    "owner_id": doc.owner_id if doc else None,
                    "file_id": doc.file_id if doc else None,
                    "mime_type": doc.mime_type if doc else "",
                    "extension": doc.extension if doc else "",
                    "file_size": doc.file_size if doc else None,
                    "content_package_id": doc.content_package_id if doc else None,
                    "parser_status": doc.parse_status if doc else "",
                    "vector_status": doc.vector_status if doc else "",
                }
            doc_info = doc_cache.get(int(doc_id), {})
            if doc_info.get("file_id"):
                file_ids.add(int(doc_info["file_id"]))

        if chunk_id:
            if int(chunk_id) not in chunk_cache:
                cr = await db.execute(
                    select(KbChunk)
                    .join(KbDocument, KbDocument.id == KbChunk.document_id)
                    .join(File, File.id == KbDocument.file_id)
                    .where(
                        KbChunk.id == int(chunk_id),
                        KbChunk.owner_id == KbDocument.owner_id,
                        KbDocument.deleted.is_(False),
                        File.deleted.is_(False),
                        _accessible_document_clause(owner_id),
                    )
                )
                chunk = cr.scalar_one_or_none()
                chunk_cache[int(chunk_id)] = {
                    "block_id": chunk.block_id if chunk else None,
                    "chunk_index": chunk.chunk_index if chunk else None,
                    "section": chunk.block_type if chunk else None,
                    "paragraph": chunk.chunk_index if chunk else None,
                }
            chunk_info = chunk_cache.get(int(chunk_id), {})

        retrieval_source = item.get("source") or "hybrid"
        item.update({
            "document_name": doc_info.get("name", ""),
            "file_id": doc_info.get("file_id"),
            "source_file_id": doc_info.get("file_id"),
            "source_file": doc_info.get("name", ""),
            "mime_type": doc_info.get("mime_type", ""),
            "extension": doc_info.get("extension", ""),
            "file_size": doc_info.get("file_size"),
            "content_package_id": doc_info.get("content_package_id"),
            "block_id": chunk_info.get("block_id"),
            "chunk_index": chunk_info.get("chunk_index"),
            "section": chunk_info.get("section"),
            "paragraph": chunk_info.get("paragraph"),
            "source_module": "knowledge",
            "source_type": "knowledge_document",
            "retrieval_source": retrieval_source,
            "explain": {
                "retrieval_source": retrieval_source,
                "score": item.get("score"),
                "rrf_score": item.get("rrf_score"),
                "doc_score": item.get("doc_score"),
                "structured_score": item.get("structured_score"),
                "kw_score": item.get("kw_score"),
                "vec_score": item.get("vec_score"),
                "retrieval_score": item.get("retrieval_score"),
                "score_breakdown": item.get("score_breakdown"),
                "doc_rank": item.get("doc_rank"),
                "structured_rank": item.get("structured_rank"),
                "kw_rank": item.get("kw_rank"),
                "vec_rank": item.get("vec_rank"),
                "final_rank": item.get("final_rank"),
                "source_file_id": doc_info.get("file_id"),
                "source_file": doc_info.get("name", ""),
                "page": page,
                "section": chunk_info.get("section"),
                "paragraph": chunk_info.get("paragraph"),
                "query_plan": item.get("query_plan"),
            },
        })
        if include_page_fusion and doc_id and page:
            item["page_fusion"] = await _get_page_fusion(
                db,
                int(doc_id),
                int(page),
                owner_id=int(doc_info["owner_id"]) if doc_info.get("owner_id") else owner_id,
            )
        enriched.append(item)

    context_data = {
        "result_count": len(enriched),
        "document_ids": sorted(document_ids),
        "file_ids": sorted(file_ids),
        "fields": [
            "chunk_id",
            "document_id",
            "file_id",
            "page",
            "section",
            "paragraph",
            "score",
            "source_file",
            "explain",
        ],
    }
    return enriched, context_data


# ── Cross-module capabilities ───────────────────────────────

def _search_resource_refs(results: list[dict]) -> list[dict]:
    refs: list[dict] = []
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("chunk_id") or item.get("document_id")
        if raw_id is None or str(raw_id) in seen:
            continue
        seen.add(str(raw_id))
        provenance = {
            key: item[key]
            for key in ("document_id", "chunk_id", "file_id", "page", "score")
            if item.get(key) is not None
        }
        refs.append({
            "type": "record",
            "id": raw_id,
            "display_name": str(
                item.get("title")
                or item.get("document_name")
                or item.get("source_file")
                or f"Knowledge evidence {raw_id}"
            ),
            "access_scope": "user",
            "provenance": {"module": "knowledge", **provenance},
        })
    return refs


async def _cap_search(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    query = str(
        params.get("query")
        or params.get("q")
        or params.get("keyword")
        or params.get("text")
        or params.get("search")
        or ""
    ).strip()
    top_k = int(params.get("top_k", 10) or 10)
    embedding_profile = params.get("embedding_profile")
    embedding_profile = str(embedding_profile).strip() if embedding_profile else None
    # 重排默认开(bge-reranker真重排):Agent检索走这条路,之前硬编码False导致召回不精
    use_rerank = bool(params.get("use_rerank", True))
    if not query:
        raise ValueError("query is required")
    async with AsyncSessionLocal() as db:
        results = await hybrid_search(
            db,
            query,
            owner_id,
            top_k=top_k,
            use_rerank=use_rerank,
            embedding_profile=embedding_profile,
        )
        enriched, context_data = await _enrich_search_results(
            db,
            results,
            owner_id,
            include_page_fusion=True,
        )
        query_context = await persist_query_context(
            db,
            owner_id=owner_id,
            query=query,
            results=enriched,
            query_plan=getattr(results, "query_plan", None),
            diagnostics=getattr(results, "diagnostics", None),
        )
        await db.commit()
        return {
            "query": query,
            "results": enriched,
            "resource_refs": _search_resource_refs(enriched),
            "context_data": {
                **context_data,
                "top_k": top_k,
                "use_rerank": False,
                "query_plan": getattr(results, "query_plan", None),
                "diagnostics": getattr(results, "diagnostics", None),
                "query_context": query_context,
            },
        }

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
        doc = await get_live_document_or_raise(db, document_id, owner_id)
        result = await get_page_fusion(db, document_id, page, owner_id=int(doc["owner_id"]))
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

async def _cap_audit_lifecycle_debt(params: dict, caller: str) -> dict:
    all_owners = bool(params.get("all_owners", False))
    owner_id = None if all_owners else resolve_user_id(caller)
    limit = int(params.get("limit", 500) or 500)
    reason = str(params.get("reason", "source_unavailable") or "source_unavailable")
    async with AsyncSessionLocal() as db:
        return await audit_lifecycle_debt(db, owner_id, limit=limit, reason=reason)

async def _cap_archive_source_unavailable_documents(params: dict, caller: str) -> dict:
    all_owners = bool(params.get("all_owners", False))
    owner_id = None if all_owners else resolve_user_id(caller)
    limit = int(params.get("limit", 100) or 100)
    reason = str(params.get("reason", "source_unavailable") or "source_unavailable")
    dry_run = bool(params.get("dry_run", True))
    confirm = str(params.get("confirm", "") or "")
    audit_reason = str(params.get("reason_text", params.get("audit_reason", "")) or "")
    async with AsyncSessionLocal() as db:
        return await archive_source_unavailable_documents(
            db,
            owner_id,
            dry_run=dry_run,
            limit=limit,
            reason=reason,
            confirm=confirm,
            audit_reason=audit_reason,
        )

async def _cap_get_evidence_detail(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    entity_id = int(params.get("entity_id", 0) or 0)
    async with AsyncSessionLocal() as db:
        result = await get_evidence_detail(db, owner_id, entity_id)
        return {"evidence": result}

async def _cap_plan_pipeline_rerun(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    document_id = int(params.get("document_id", 0) or 0)
    if document_id <= 0:
        raise ValueError("document_id must be positive")
    reason = str(params.get("reason", "") or "").strip()
    stage = params.get("stage")
    async with AsyncSessionLocal() as db:
        return await plan_pipeline_rerun(
            db,
            document_id=document_id,
            owner_id=owner_id,
            reason=reason,
            stage=str(stage) if stage else None,
        )

async def _cap_backfill_cognitive_index(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    dry_run = bool(params.get("dry_run", True))
    limit = int(params.get("limit", 1000) or 1000)
    source_root = str(params.get("source_root", "") or "")
    build_terms = bool(params.get("build_terms", True))
    async with AsyncSessionLocal() as db:
        if not dry_run:
            await ensure_accepting_new_work(db, "knowledge backfill")
        return await backfill_cognitive_index(
            db,
            owner_id=owner_id,
            dry_run=dry_run,
            limit=limit,
            source_root=source_root,
            build_terms=build_terms,
        )

async def _cap_derive_cognitive_index(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    document_id = int(params.get("document_id", 0) or 0)
    if document_id <= 0:
        raise ValueError("document_id must be positive")
    limit = int(params.get("limit", 200) or 200)
    async with AsyncSessionLocal() as db:
        await ensure_accepting_new_work(db, "knowledge backfill")
        await get_live_document_or_raise(db, document_id, owner_id)
        result = await derive_document_cognitive_index(
            db,
            owner_id=owner_id,
            document_id=document_id,
            limit=limit,
        )
        await db.commit()
        return result

async def _cap_backfill_derived_governance(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    dry_run = bool(params.get("dry_run", True))
    limit = int(params.get("limit", 5000) or 5000)
    async with AsyncSessionLocal() as db:
        if not dry_run:
            await ensure_accepting_new_work(db, "knowledge backfill")
        return await backfill_derived_governance(
            db,
            owner_id=owner_id,
            dry_run=dry_run,
            limit=limit,
            include_lineage=bool(params.get("include_lineage", True)),
            include_conclusion_evidence=bool(params.get("include_conclusion_evidence", True)),
            include_entity_aliases=bool(params.get("include_entity_aliases", True)),
            include_disambiguation=bool(params.get("include_disambiguation", True)),
        )

async def _cap_get_derived_governance_counts(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    _ = params
    async with AsyncSessionLocal() as db:
        return await derived_governance_counts(db, owner_id=owner_id)

async def _cap_reflect_retrieval_feedback(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    query_context_id = int(params.get("query_context_id", 0) or 0)
    if query_context_id <= 0:
        raise ValueError("query_context_id must be positive")
    conversation_excerpt = str(params.get("conversation_excerpt", "") or "").strip()
    if not conversation_excerpt:
        raise ValueError("conversation_excerpt is required")
    async with AsyncSessionLocal() as db:
        await ensure_accepting_new_work(db, "knowledge reflection")
        result = await reflect_retrieval_feedback(
            db,
            owner_id=owner_id,
            query_context_id=query_context_id,
            conversation_excerpt=conversation_excerpt,
        )
        await db.commit()
        return result

async def _cap_get_chunk_embedding_counts(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    embedding_profile = str(
        params.get("embedding_profile") or DEFAULT_CHUNK_EMBEDDING_PROFILE
    ).strip()
    async with AsyncSessionLocal() as db:
        return await get_chunk_embedding_counts(db, owner_id=owner_id, profile_key=embedding_profile)

async def _cap_backfill_chunk_embeddings(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    embedding_profile = str(
        params.get("embedding_profile") or DEFAULT_CHUNK_EMBEDDING_PROFILE
    ).strip()
    dry_run = bool(params.get("dry_run", True))
    limit = int(params.get("limit", 1000) or 1000)
    batch_size = int(params.get("batch_size", 8) or 8)
    async with AsyncSessionLocal() as db:
        if not dry_run:
            await ensure_accepting_new_work(db, "knowledge backfill")
        return await backfill_chunk_embeddings(
            db,
            owner_id=owner_id,
            profile_key=embedding_profile,
            dry_run=dry_run,
            limit=limit,
            batch_size=batch_size,
        )

async def _cap_enqueue_chunk_embedding_backfill(params: dict, caller: str) -> dict:
    actor_id = resolve_user_id(caller)
    owner_id = int(params.get("owner_id") or actor_id)
    embedding_profile = str(
        params.get("embedding_profile") or DEFAULT_CHUNK_EMBEDDING_PROFILE
    ).strip()
    total_limit = int(params.get("total_limit", 600000) or 600000)
    chunk_limit = int(params.get("chunk_limit", 96) or 96)
    batch_size = int(params.get("batch_size", 4) or 4)
    priority = int(params.get("priority", 4) or 4)
    async with AsyncSessionLocal() as db:
        await ensure_accepting_new_work(db, "knowledge chunk embedding backfill")
        result = await enqueue_chunk_embedding_backfill_task(
            db,
            owner_id=owner_id,
            profile_key=embedding_profile,
            total_limit=total_limit,
            chunk_limit=chunk_limit,
            batch_size=batch_size,
            priority=priority,
        )
        await db.commit()
        return result

async def _cap_enqueue_pipeline_stage_batch(params: dict, caller: str) -> dict:
    actor_id = resolve_user_id(caller)
    owner_id = int(params.get("owner_id") or actor_id)
    stage = str(params.get("stage") or "").strip()
    dry_run = bool(params.get("dry_run", True))
    limit = int(params.get("limit", 20) or 20)
    priority = int(params.get("priority", 5) or 5)
    confirm = str(params.get("confirm", "") or "")
    audit_reason = str(params.get("audit_reason", "") or "")
    filename_contains = str(params.get("filename_contains", "") or "")
    document_ids_param = params.get("document_ids") or []
    document_ids = (
        [int(item) for item in document_ids_param]
        if isinstance(document_ids_param, list)
        else []
    )
    extensions_param = params.get("extensions") or []
    if isinstance(extensions_param, str):
        extensions = [part.strip() for part in extensions_param.split(",") if part.strip()]
    elif isinstance(extensions_param, list):
        extensions = [str(part).strip() for part in extensions_param if str(part).strip()]
    else:
        extensions = []
    async with AsyncSessionLocal() as db:
        if not dry_run:
            await ensure_accepting_new_work(db, "knowledge single-stage batch")
        return await enqueue_pipeline_stage_batch(
            db,
            actor_id=actor_id,
            owner_id=owner_id,
            stage=stage,
            dry_run=dry_run,
            confirm=confirm,
            audit_reason=audit_reason,
            limit=limit,
            document_ids=document_ids,
            extensions=extensions,
            filename_contains=filename_contains,
            priority=priority,
        )

async def _cap_enqueue_incomplete_documents(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    dry_run = bool(params.get("dry_run", True))
    limit = int(params.get("limit", 20) or 20)
    priority = int(params.get("priority", 5) or 5)
    extensions_param = params.get("extensions") or []
    if isinstance(extensions_param, str):
        extensions = [part.strip() for part in extensions_param.split(",") if part.strip()]
    elif isinstance(extensions_param, list):
        extensions = [str(part).strip() for part in extensions_param if str(part).strip()]
    else:
        extensions = []
    include_search_incomplete = bool(params.get("include_search_incomplete", True))
    async with AsyncSessionLocal() as db:
        return await enqueue_incomplete_documents(
            db,
            owner_id=owner_id,
            limit=limit,
            dry_run=dry_run,
            extensions=extensions,
            priority=priority,
            include_search_incomplete=include_search_incomplete,
        )

async def _cap_import_enterprise_source_batch(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    source_root = str(params.get("source_root", "") or "")
    target_root_name = str(params.get("target_root_name", "企业微盘导入") or "企业微盘导入")
    dry_run = bool(params.get("dry_run", True))
    limit = int(params.get("limit", 20) or 20)
    skip_existing_md5 = bool(params.get("skip_existing_md5", True))
    extensions_param = params.get("extensions") or []
    if isinstance(extensions_param, str):
        extensions = [part.strip() for part in extensions_param.split(",") if part.strip()]
    elif isinstance(extensions_param, list):
        extensions = [str(part).strip() for part in extensions_param if str(part).strip()]
    else:
        extensions = []
    async with AsyncSessionLocal() as db:
        if not dry_run:
            await ensure_accepting_new_work(db, "enterprise source batch import")
        return await import_enterprise_source_batch(
            db,
            owner_id=owner_id,
            source_root=source_root,
            target_root_name=target_root_name,
            limit=limit,
            dry_run=dry_run,
            extensions=extensions,
            skip_existing_md5=skip_existing_md5,
        )

async def _cap_enqueue_enterprise_source_import(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    source_root = str(params.get("source_root", "") or "")
    target_root_name = str(params.get("target_root_name", "企业微盘导入") or "企业微盘导入")
    batch_size = int(params.get("batch_size", 200) or 200)
    priority = int(params.get("priority", 12) or 12)
    skip_existing_md5 = bool(params.get("skip_existing_md5", True))
    extensions_param = params.get("extensions") or []
    if isinstance(extensions_param, str):
        extensions = [part.strip() for part in extensions_param.split(",") if part.strip()]
    elif isinstance(extensions_param, list):
        extensions = [str(part).strip() for part in extensions_param if str(part).strip()]
    else:
        extensions = []
    async with AsyncSessionLocal() as db:
        return await enqueue_enterprise_source_import(
            db,
            owner_id=owner_id,
            source_root=source_root,
            target_root_name=target_root_name,
            extensions=extensions,
            skip_existing_md5=skip_existing_md5,
            batch_size=batch_size,
            priority=priority,
        )

async def _cap_scan_source_manifest(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    source_root = str(params.get("source_root", "") or "")
    target_root_name = str(params.get("target_root_name", "企业微盘导入") or "企业微盘导入")
    limit = int(params.get("limit", 10000) or 10000)
    mark_missing = bool(params.get("mark_missing", False))
    extensions_param = params.get("extensions") or []
    if isinstance(extensions_param, str):
        extensions = [part.strip() for part in extensions_param.split(",") if part.strip()]
    elif isinstance(extensions_param, list):
        extensions = [str(part).strip() for part in extensions_param if str(part).strip()]
    else:
        extensions = []
    async with AsyncSessionLocal() as db:
        if mark_missing:
            await ensure_accepting_new_work(db, "source manifest scan")
        return await scan_source_manifest(
            db,
            owner_id=owner_id,
            source_root=source_root,
            target_root_name=target_root_name,
            extensions=extensions,
            limit=limit,
            mark_missing=mark_missing,
        )

async def _cap_source_manifest_summary(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    source_root = str(params.get("source_root", "") or "").strip() or None
    async with AsyncSessionLocal() as db:
        return await source_manifest_summary(db, owner_id=owner_id, source_root=source_root)

async def _cap_enqueue_source_manifest_import(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    source_root = str(params.get("source_root", "") or "")
    target_root_name = str(params.get("target_root_name", "企业微盘导入") or "企业微盘导入")
    limit = int(params.get("limit", 1000) or 1000)
    priority = int(params.get("priority", 8) or 8)
    skip_existing_md5 = bool(params.get("skip_existing_md5", True))
    extensions_param = params.get("extensions") or []
    if isinstance(extensions_param, str):
        extensions = [part.strip() for part in extensions_param.split(",") if part.strip()]
    elif isinstance(extensions_param, list):
        extensions = [str(part).strip() for part in extensions_param if str(part).strip()]
    else:
        extensions = []
    async with AsyncSessionLocal() as db:
        return await enqueue_source_manifest_import(
            db,
            owner_id=owner_id,
            source_root=source_root,
            target_root_name=target_root_name,
            extensions=extensions,
            limit=limit,
            priority=priority,
            skip_existing_md5=skip_existing_md5,
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

async def _cap_get_ingest_status(params: dict, caller: str) -> dict:
    owner_id = resolve_user_id(caller)
    document_id = int(params.get("document_id", 0) or 0)
    if document_id <= 0:
        raise ValueError("document_id must be positive")
    async with AsyncSessionLocal() as db:
        return await get_ingest_status(db, document_id, owner_id)

async def _cap_export(params: dict, caller: str) -> dict:
    from app.database import AsyncSessionLocal

    from .services.export_service import export_document

    document_id = int(params.get("document_id", 0))
    fmt = str(params.get("format", "markdown") or "markdown").lower().strip()
    if document_id <= 0:
        return {"success": False, "error": "document_id is required"}
    if fmt not in {"markdown", "html", "json"}:
        return {"success": False, "error": "Unsupported export format. Use markdown, html, or json."}

    owner_id = None
    if caller.startswith("user:"):
        owner_id = int(caller.split(":", 1)[1])

    async with AsyncSessionLocal() as db:
        if owner_id is not None:
            doc = await get_live_document_or_raise(db, document_id, owner_id)
            effective_owner_id = int(doc["owner_id"])
        else:
            effective_owner_id = owner_id
        result = await export_document(db, document_id, fmt=fmt, owner_id=effective_owner_id)
        if not result.get("success"):
            return {"success": False, "error": str(result.get("error") or "Export failed")}
        return result

# ── Capability registrations ──────────────────────────────────────
register_capability(
    "knowledge", "search", _cap_search,
    description="Search enterprise knowledge base and return relevant text chunks with source metadata",
    brief="检索知识库",
    parameters={
        "query": {"type": "string", "description": "Search query"},
        "top_k": {"type": "integer", "description": "Number of results, default 5"},
        "embedding_profile": {
            "type": "string",
            "description": "Optional embedding profile key, e.g. qwen3-embedding-8b",
        },
    },
    min_role="viewer",
    execution_contract={
        "output_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "results": {"type": "array"},
                "context_data": {"type": "object"},
                "resource_refs": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["query", "results", "context_data", "resource_refs"],
        },
        "execution_mode": "sync",
        "resource_class": "local_cpu",
        "timeout_seconds": 120,
        "max_attempts": 1,
        "idempotency": "supported",
        "side_effect_level": "none",
        "output_reference_types": ["record"],
        "parallel_safe": True,
    },
    retrieval={
        "aliases": ["知识库检索", "内部资料搜索", "企业文档问答"],
        "when_to_use": "用户询问公司内部资料、已入库文档或需要可追溯知识证据时",
        "when_not_to_use": "用户只需要公开网络资料或不依赖企业知识时",
        "input_reference_types": [],
    },
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
    "knowledge", "classify_pipeline_debt", cap_classify_pipeline_debt,
    description="Dry-run classify historical knowledge pipeline debt without mutating queue rows",
    brief="分类知识库管道债",
    parameters={
        "limit": {"type": "integer", "description": "Maximum failed tasks to inspect, default 500"},
        "category": {"type": "string", "description": "Optional comma-separated category filter"},
        "categories": {"type": "array", "description": "Optional category filters"},
        "category_limits": {"type": "object", "description": "Optional per-category limits, e.g. {doc_missing: 20}"},
        "limit_each": {"type": "integer", "description": "Optional default per-category limit"},
        "order": {"type": "string", "description": "Candidate order: newest or oldest"},
        "task_ids": {"type": "array", "description": "Optional exact task IDs; bypasses per-category limits"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "apply_pipeline_debt", cap_apply_pipeline_debt,
    description="Dry-run or apply guarded remediation for historical knowledge pipeline debt",
    brief="治理知识库管道债",
    parameters={
        "action": {"type": "string", "description": "archive_obsolete or retry_live"},
        "limit": {"type": "integer", "description": "Maximum failed tasks to inspect, default 500"},
        "task_ids": {"type": "array", "description": "Optional exact task IDs; bypasses per-category limits"},
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
        "category": {"type": "string", "description": "Optional comma-separated category filter"},
        "categories": {"type": "array", "description": "Optional category filters"},
        "category_limits": {"type": "object", "description": "Optional per-category limits, e.g. {doc_missing: 20}"},
        "limit_each": {"type": "integer", "description": "Optional default per-category limit"},
        "order": {"type": "string", "description": "Candidate order: newest or oldest"},
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
    "knowledge", "reconcile_pending_pipeline_queue", cap_reconcile_pending_pipeline_queue,
    description="Dry-run or archive obsolete pending knowledge pipeline queue rows while leaving live pending work untouched",
    brief="收口过期待处理队列",
    parameters={
        "limit": {"type": "integer", "description": "Maximum pending tasks to inspect, default 500"},
        "task_ids": {"type": "array", "description": "Optional exact task IDs; bypasses category limits"},
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
        "category": {"type": "string", "description": "Optional comma-separated category filter"},
        "categories": {"type": "array", "description": "Optional category filters"},
        "category_limits": {"type": "object", "description": "Optional per-category limits"},
        "limit_each": {"type": "integer", "description": "Optional default per-category limit"},
        "order": {"type": "string", "description": "Candidate order: newest or oldest"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "reconcile_running_pipeline_queue", cap_reconcile_running_pipeline_queue,
    description="Dry-run or recover interrupted running knowledge pipeline queue rows by requeueing live tasks or skipping obsolete rows",
    brief="收口中断运行队列",
    parameters={
        "limit": {"type": "integer", "description": "Maximum running tasks to inspect, default 500"},
        "task_ids": {"type": "array", "description": "Optional exact task IDs; bypasses category limits"},
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
        "category": {"type": "string", "description": "Optional comma-separated category filter"},
        "categories": {"type": "array", "description": "Optional category filters"},
        "category_limits": {"type": "object", "description": "Optional per-category limits"},
        "limit_each": {"type": "integer", "description": "Optional default per-category limit"},
        "order": {"type": "string", "description": "Candidate order: newest or oldest"},
    },
    min_role="admin",
)

register_capability(
    "knowledge", "audit_lifecycle_debt", _cap_audit_lifecycle_debt,
    description="Audit active knowledge documents whose source files are recycled, missing, path-invalid, or physically missing",
    brief="审计知识库源文件债",
    parameters={
        "limit": {"type": "integer", "description": "Maximum candidate documents to return, default 500"},
        "all_owners": {"type": "boolean", "description": "Admin-only full-owner audit when true, default false"},
        "reason": {
            "type": "string",
            "description": (
                "source_file_deleted, source_file_missing, source_storage_path_missing, "
                "source_path_unsafe, source_file_physical_missing, or source_unavailable"
            ),
        },
    },
    min_role="admin",
)
register_capability(
    "knowledge", "archive_source_unavailable_documents", _cap_archive_source_unavailable_documents,
    description="Dry-run or archive active knowledge documents whose source files are unavailable",
    brief="归档源不可用文档",
    parameters={
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
        "limit": {"type": "integer", "description": "Maximum documents to archive, default 100"},
        "all_owners": {"type": "boolean", "description": "Admin-only full-owner archive when true, default false"},
        "reason": {
            "type": "string",
            "description": (
                "source_file_deleted, source_file_missing, source_storage_path_missing, "
                "source_path_unsafe, source_file_physical_missing, or source_unavailable"
            ),
        },
        "confirm": {"type": "string", "description": "ARCHIVE_SOURCE_UNAVAILABLE required for apply"},
        "audit_reason": {"type": "string", "description": "Operator reason recorded in result"},
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
register_capability(
    "knowledge", "plan_pipeline_rerun", _cap_plan_pipeline_rerun,
    description="Dry-run a knowledge pipeline rerun plan without mutating artifacts or queue tasks",
    brief="规划知识库重跑",
    parameters={
        "document_id": {"type": "integer", "description": "Document ID"},
        "reason": {"type": "string", "description": "prompt_changed/schema_changed/model_changed/source_changed/vlm_preprocess_changed/manual_failed_retry"},
        "stage": {"type": "string", "description": "Optional starting stage: raw/fusion/profile/graph/relations"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "backfill_cognitive_index", _cap_backfill_cognitive_index,
    description="Backfill Knowledge content links, validation batch report, and optional derived cognitive indexes",
    brief="回填知识库认知账本",
    parameters={
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
        "limit": {"type": "integer", "description": "Maximum files to inspect, default 1000"},
        "source_root": {"type": "string", "description": "Optional import source label for the batch report"},
        "build_terms": {"type": "boolean", "description": "Build term/fact/causal derived indexes when applying"},
    },
    min_role="admin",
)

register_capability(
    "knowledge", "derive_cognitive_index", _cap_derive_cognitive_index,
    description="Rebuild derived term, fact, and causal candidates for one knowledge document",
    brief="重建文档认知索引",
    parameters={
        "document_id": {"type": "integer", "description": "Document ID"},
        "limit": {"type": "integer", "description": "Maximum terms per source text, default 200"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "backfill_derived_governance", _cap_backfill_derived_governance,
    description=(
        "Backfill derived governance side indexes from existing analysis artifacts, "
        "fact candidates, and entity dictionary rows"
    ),
    brief="回填知识库派生治理索引",
    parameters={
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
        "limit": {"type": "integer", "description": "Maximum source rows to inspect per index, default 5000"},
        "include_lineage": {"type": "boolean", "description": "Backfill kb_artifact_lineage, default true"},
        "include_conclusion_evidence": {
            "type": "boolean",
            "description": "Backfill kb_conclusion_evidence from fact candidates, default true",
        },
        "include_entity_aliases": {
            "type": "boolean",
            "description": "Backfill kb_entity_aliases from open-ended entity name variants, default true",
        },
        "include_disambiguation": {
            "type": "boolean",
            "description": "Backfill kb_disambiguation from alias/name collisions, default true",
        },
    },
    min_role="admin",
)
register_capability(
    "knowledge", "get_derived_governance_counts", _cap_get_derived_governance_counts,
    description="Count derived governance side-index rows for the current owner",
    brief="统计派生治理索引",
    parameters={},
    min_role="admin",
)
register_capability(
    "knowledge", "reflect_retrieval_feedback", _cap_reflect_retrieval_feedback,
    description="Use later conversation excerpts to infer implicit feedback for a persisted knowledge search query context",
    brief="复盘知识库检索反馈",
    parameters={
        "query_context_id": {"type": "integer", "description": "Persisted kb_query_contexts ID"},
        "conversation_excerpt": {"type": "string", "description": "Later conversation excerpt after the search"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "get_chunk_embedding_counts", _cap_get_chunk_embedding_counts,
    description="Count versioned chunk embedding sidecar coverage for a configured embedding profile",
    brief="统计块向量覆盖率",
    parameters={
        "embedding_profile": {
            "type": "string",
            "description": "Embedding profile key, default qwen3-embedding-8b",
        },
    },
    min_role="admin",
)

register_capability(
    "knowledge", "backfill_chunk_embeddings", _cap_backfill_chunk_embeddings,
    description="Dry-run or backfill versioned chunk embeddings into the configured sidecar vector store",
    brief="补跑块向量边车",
    parameters={
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
        "limit": {"type": "integer", "description": "Maximum chunks to inspect/backfill, default 1000"},
        "batch_size": {"type": "integer", "description": "Embedding batch size, default 8"},
        "embedding_profile": {
            "type": "string",
            "description": "Embedding profile key, default qwen3-embedding-8b",
        },
    },
    min_role="admin",
)
register_capability(
    "knowledge", "enqueue_chunk_embedding_backfill", _cap_enqueue_chunk_embedding_backfill,
    description="Enqueue queued Qwen3 chunk embedding sidecar backfill work; worker auto-starts the local model as needed",
    brief="入队块向量边车补跑",
    parameters={
        "total_limit": {"type": "integer", "description": "Maximum chunks to backfill across chained tasks, default 600000"},
        "chunk_limit": {"type": "integer", "description": "Chunks per queued task, default 96"},
        "batch_size": {"type": "integer", "description": "Embedding batch size, default 4"},
        "priority": {"type": "integer", "description": "Queue priority, default 4"},
        "embedding_profile": {
            "type": "string",
            "description": "Embedding profile key, default qwen3-embedding-8b",
        },
    },
    min_role="admin",
)
register_capability(
    "knowledge", "enqueue_pipeline_stage_batch", _cap_enqueue_pipeline_stage_batch,
    description="Preview or enqueue one bounded Knowledge cloud stage for a target owner without publishing downstream stages",
    brief="受控投递单阶段知识分析",
    parameters={
        "owner_id": {"type": "integer", "description": "Target Knowledge owner ID; defaults to caller"},
        "stage": {"type": "string", "description": "Allowed stage: raw_ocr, raw_vision, or fusion"},
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
        "confirm": {"type": "string", "description": "ENQUEUE_KNOWLEDGE_STAGE_BATCH required for apply"},
        "audit_reason": {"type": "string", "description": "Operator reason recorded with queued work"},
        "limit": {"type": "integer", "description": "Maximum documents to select, default 20, capped at 500"},
        "document_ids": {"type": "array", "description": "Optional exact document IDs within target owner"},
        "extensions": {"type": "array", "description": "Optional extension filter, e.g. [pdf]"},
        "filename_contains": {"type": "string", "description": "Optional case-insensitive filename filter"},
        "priority": {"type": "integer", "description": "Queue priority, default 5"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "enqueue_incomplete_documents", _cap_enqueue_incomplete_documents,
    description="Preview or enqueue live knowledge documents whose deep pipeline is not complete",
    brief="补排未完成知识分析",
    parameters={
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
        "limit": {"type": "integer", "description": "Maximum documents to inspect/enqueue, default 20"},
        "extensions": {"type": "array", "description": "Optional extension filter, e.g. [pdf, docx, jpg]"},
        "priority": {"type": "integer", "description": "Queue priority for newly enqueued tasks, default 5"},
        "include_search_incomplete": {
            "type": "boolean",
            "description": "Also include documents whose parse/vector/raw/fusion stages are incomplete, default true",
        },
    },
    min_role="admin",
)

register_capability(
    "knowledge", "import_enterprise_source_batch", _cap_import_enterprise_source_batch,
    description="Dry-run or import a bounded enterprise source-folder batch into files and knowledge pipeline",
    brief="批量导入企业资料",
    parameters={
        "source_root": {"type": "string", "description": "Local source directory to scan"},
        "target_root_name": {"type": "string", "description": "Target root folder name, default 企业微盘导入"},
        "dry_run": {"type": "boolean", "description": "Preview only when true, default true"},
        "limit": {"type": "integer", "description": "Maximum files to import, default 20, capped at 200"},
        "extensions": {"type": "array", "description": "Optional extension filter"},
        "skip_existing_md5": {"type": "boolean", "description": "Skip owner files with existing md5, default true"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "enqueue_enterprise_source_import", _cap_enqueue_enterprise_source_import,
    description="Enqueue a durable background enterprise source-folder import that loops in bounded batches",
    brief="后台导入企业资料",
    parameters={
        "source_root": {"type": "string", "description": "Local source directory to scan"},
        "target_root_name": {"type": "string", "description": "Target root folder name, default 企业微盘导入"},
        "batch_size": {"type": "integer", "description": "Files per internal batch, default 200, capped at 200"},
        "extensions": {"type": "array", "description": "Optional extension filter"},
        "skip_existing_md5": {"type": "boolean", "description": "Reuse existing content by md5, default true"},
        "priority": {"type": "integer", "description": "Background import task priority, default 12"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "scan_source_manifest", _cap_scan_source_manifest,
    description="Scan an external physical source directory into a durable manifest without importing files",
    brief="扫描外部源清单",
    parameters={
        "source_root": {"type": "string", "description": "Local source directory to scan"},
        "target_root_name": {"type": "string", "description": "Target root folder name for later import"},
        "limit": {"type": "integer", "description": "Maximum files to scan in this call, default 10000"},
        "extensions": {"type": "array", "description": "Optional extension filter"},
        "mark_missing": {"type": "boolean", "description": "Mark previously seen files absent from this full scan as missing"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "source_manifest_summary", _cap_source_manifest_summary,
    description="Summarize external source manifest rows by root, extension, and import status",
    brief="外部源清单汇总",
    parameters={
        "source_root": {"type": "string", "description": "Optional source root filter"},
    },
    min_role="admin",
)
register_capability(
    "knowledge", "enqueue_source_manifest_import", _cap_enqueue_source_manifest_import,
    description="Enqueue import tasks for discovered or changed external source manifest rows",
    brief="投递外部源清单导入",
    parameters={
        "source_root": {"type": "string", "description": "Manifest source root to import from"},
        "target_root_name": {"type": "string", "description": "Target root folder name"},
        "limit": {"type": "integer", "description": "Maximum manifest rows to enqueue, default 1000"},
        "extensions": {"type": "array", "description": "Optional extension filter"},
        "skip_existing_md5": {"type": "boolean", "description": "Reuse existing content by md5, default true"},
        "priority": {"type": "integer", "description": "Background import task priority, default 8"},
    },
    min_role="admin",
)
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
register_capability(
    "knowledge", "ingest", _cap_ingest,
    description="把已上传文件登记进知识库并触发后台分析（幂等、类型白名单）",
    brief="文件入库知识库",
    parameters={"file_id": {"type": "integer", "description": "Uploaded file ID"}},
    min_role="editor",
)
register_capability(
    "knowledge", "get_ingest_status", _cap_get_ingest_status,
    description="Get unified knowledge ingest status for a document, including queue task and stage readiness",
    brief="查询入库状态",
    parameters={"document_id": {"type": "integer", "description": "Document ID"}},
    min_role="viewer",
)
register_capability(
    "knowledge", "export", _cap_export,
    description="导出已解析文档（markdown/html/json）",
    brief="导出文档",
    parameters={"document_id": {"type": "integer"}, "format": {"type": "string"}},
    min_role="viewer",
)

# ── Event handler ─────────────────────────────────────────────────
async def _on_file_uploaded(payload: dict, caller: str, caller_role: str) -> dict:
    """Handle file.uploaded event: register file into knowledge base.

    Reuses _cap_ingest logic (type whitelist, idempotent, permission check).
    This is best-effort: failures are logged but do not block the upload flow.
    """
    return await _cap_ingest(payload, caller)

register_module_event_handler("file.uploaded", _on_file_uploaded, "knowledge")


# ── 语义打齐批量能力(供回填脚本 HTTP 调用,复用常驻底座) ───────────
async def _cap_align_entity_batch(params: dict, caller: str) -> dict:
    """对一批实体执行 canonicalize_name(逐字位打齐+护栏8裁定),标记 align_status。"""
    from app.database import AsyncSessionLocal
    from .services.semantic_align_service import canonicalize_name, _resolve_canonical_entity, _merge_variant_into

    owner_id = int(caller.split(":")[1]) if ":" in caller else 4
    batch = int(params.get("batch", 100))
    gate = bool(params.get("gate", True))
    shard = int(params.get("shard", 0))
    shards = max(1, int(params.get("shards", 1)))

    async with AsyncSessionLocal() as db:
        from sqlalchemy import text as T
        r = await db.execute(T("""
            SELECT ed.id, ed.name, ed.category
            FROM kb_entity_dictionary ed
            WHERE ed.owner_id=:o AND ed.status!='merged'
              AND COALESCE(ed.align_status,'pending')='pending'
              AND ed.name ~ '[一-鿿]' AND length(ed.name)>=2
              AND (mod(ed.id, :shards) = :shard)
              AND EXISTS (SELECT 1 FROM kb_chunk_entities ce WHERE ce.entity_id=ed.id AND ce.owner_id=:o)
            ORDER BY length(ed.name), ed.id
            LIMIT :b
        """), {"o": owner_id, "b": batch, "shards": shards, "shard": shard})
        ents = [(int(i), n, c) for i, n, c in r.all()]

    if not ents:
        return {"success": True, "data": {"checked": 0, "aligned": 0, "remaining": 0}}

    import asyncio as _aio
    import logging as _log
    batch_conc = int(params.get("batch_conc", 8))  # 批内并发(热调,防打爆DB)
    sem = _aio.Semaphore(batch_conc)
    counters = {"checked": 0, "aligned": 0}

    async def _处理一条(eid, name, category):
        async with sem:
            try:
                async with AsyncSessionLocal() as db:
                    canonical_name, fixes = await canonicalize_name(db, owner_id, name, semantic_gate=gate)
                    if fixes and canonical_name != name:
                        cid = await _resolve_canonical_entity(db, owner_id, canonical_name, category)
                        await _merge_variant_into(db, owner_id, eid, name, cid, canonical_name, fixes)
                        await db.commit()
                        counters["aligned"] += 1
                    await db.execute(T("UPDATE kb_entity_dictionary SET align_status='done' WHERE owner_id=:o AND id=:id"),
                                     {"o": owner_id, "id": eid})
                    await db.commit()
            except Exception as exc:
                _log.getLogger(__name__).warning("align实体%d(%s)异常: %s", eid, name, str(exc)[:120])
            finally:
                counters["checked"] += 1

    await _aio.gather(*(_处理一条(eid, name, category) for eid, name, category in ents))
    checked, aligned = counters["checked"], counters["aligned"]

    # 剩余数
    async with AsyncSessionLocal() as db:
        from sqlalchemy import text as T
        r2 = await db.execute(T("""
            SELECT count(*) FROM kb_entity_dictionary ed
            WHERE ed.owner_id=:o AND ed.status!='merged'
              AND COALESCE(ed.align_status,'pending')='pending'
              AND ed.name ~ '[一-鿿]' AND length(ed.name)>=2
              AND (mod(ed.id, :shards) = :shard)
              AND EXISTS (SELECT 1 FROM kb_chunk_entities ce WHERE ce.entity_id=ed.id AND ce.owner_id=:o)
        """), {"o": owner_id, "shards": shards, "shard": shard})
        remaining = int(r2.first()[0])

    return {"success": True, "data": {"checked": checked, "aligned": aligned, "remaining": remaining}}


register_capability(
    "knowledge", "align_entity_batch", _cap_align_entity_batch,
    description="批量实体语义打齐(逐字位纠错+护栏8证据驱动裁定),回填脚本专用",
    brief="实体打齐回填",
    parameters={
        "batch": {"type": "integer", "description": "本次处理条数,默认100"},
        "gate": {"type": "boolean", "description": "是否开启护栏8(LLM裁定),默认true"},
        "shard": {"type": "integer", "description": "分片号(并行用)"},
        "shards": {"type": "integer", "description": "总分片数"},
    },
    min_role="admin",
)
