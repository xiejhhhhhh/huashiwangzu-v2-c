"""知识库文档管理服务：资料登记、解析入库、页级融合、索引状态。"""
import json
import logging
from datetime import datetime, timezone

from app.core.exceptions import AppException, NotFound, ValidationError
from app.models.file import File
from app.services.file_reader import resolve_caller_user_id as resolve_user_id  # noqa: F401
from app.services.file_service import check_file_access
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..ir_models import to_legacy_dict
from .embedding_service import chunk_and_embed, store_chunks
from .entity_service import fuse_page_text, process_document_entities
from .parsing_service import parse_document

logger = logging.getLogger("v2.knowledge").getChild("document")

SUPPORTED_EXTENSIONS = {
    "pdf", "docx", "pptx", "xlsx", "csv", "tsv", "txt", "md", "markdown",
    "json", "yaml", "yml", "eml", "msg",
    "png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "svg",
}

_ACTIVE_OR_SOURCE_ERROR_STATUSES = {
    "parsing", "indexing", "collecting", "running", "error", "failed",
}
SOURCE_UNAVAILABLE_REASONS = {"source_file_deleted", "source_file_missing"}
PARSER_NO_CONTENT_MARKER = "Parser returned no content blocks"


def document_source_unavailable_reason(doc) -> str | None:
    """Return the durable source-unavailable reason stored on a document."""
    reason = (doc.parse_error or "").strip()
    return reason if reason in SOURCE_UNAVAILABLE_REASONS else None


def document_pipeline_complete(doc, *, source_available: bool | None = None) -> bool:
    """Return whether the durable knowledge pipeline has fully completed."""
    if source_available is False or document_source_unavailable_reason(doc):
        return False
    return (
        document_parse_allows_search(doc)
        and doc.vector_status == "done"
        and getattr(doc, "raw_status", "pending") == "done"
        and getattr(doc, "fusion_status", "pending") == "done"
    )


def document_parse_allows_search(doc) -> bool:
    """Return whether parse state can support a searchable document."""
    if document_source_unavailable_reason(doc):
        return False
    if doc.parse_status == "done":
        return True
    return (
        doc.parse_status == "degraded"
        and PARSER_NO_CONTENT_MARKER.lower() in (doc.parse_error or "").lower()
    )


def mark_document_source_unavailable(doc, reason: str) -> None:
    """Pause transient pipeline state when the source file is intentionally unavailable."""
    if doc.parse_status in _ACTIVE_OR_SOURCE_ERROR_STATUSES:
        doc.parse_status = "pending"
    if doc.vector_status in _ACTIVE_OR_SOURCE_ERROR_STATUSES:
        doc.vector_status = "pending"
    if getattr(doc, "raw_status", "pending") in _ACTIVE_OR_SOURCE_ERROR_STATUSES:
        doc.raw_status = "pending"
    if getattr(doc, "fusion_status", "pending") in _ACTIVE_OR_SOURCE_ERROR_STATUSES:
        doc.fusion_status = "pending"
    doc.parse_error = reason[:2000]


async def _find_inflight_pipeline_task(db: AsyncSession, document_id: int):
    from app.models.system import SystemTaskQueue

    result = await db.execute(
        select(SystemTaskQueue).where(
            SystemTaskQueue.task_type == "kb_pipeline",
            SystemTaskQueue.module == "knowledge",
            SystemTaskQueue.status.in_(("pending", "running")),
        )
    )
    for task in result.scalars().all():
        try:
            params = json.loads(task.parameters or "{}")
        except json.JSONDecodeError:
            continue
        if int(params.get("document_id", 0) or 0) == int(document_id):
            return task
    return None


async def enqueue_pipeline_task(
    db: AsyncSession,
    doc,
    user_id: int,
    *,
    force_raw: bool = False,
    force_fusion: bool = False,
    priority: int = 5,
) -> dict:
    """Enqueue one kb_pipeline task, deduping pending/running work for the document."""
    from app.models.system import SystemTaskQueue

    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :document_id)"),
        {"namespace": 1262633036, "document_id": int(doc.id) % 2147483647},
    )
    existing = await _find_inflight_pipeline_task(db, int(doc.id))
    if existing:
        return {
            "task_id": existing.id,
            "enqueued": False,
            "reason": "already_in_flight",
        }

    task = SystemTaskQueue(
        task_type="kb_pipeline",
        module="knowledge",
        parameters=json.dumps({
            "document_id": doc.id,
            "user_id": user_id,
            "force_raw": force_raw,
            "force_fusion": force_fusion,
        }, ensure_ascii=False),
        priority=priority,
        status="pending",
        creator_id=user_id,
    )
    db.add(task)
    await db.flush()
    task.parameters = json.dumps({
        "document_id": doc.id,
        "user_id": user_id,
        "force_raw": force_raw,
        "force_fusion": force_fusion,
        "task_id": task.id,
    }, ensure_ascii=False)
    return {"task_id": task.id, "enqueued": True, "reason": "created"}


async def _count_document_chunks(db: AsyncSession, document_id: int) -> int:
    from ..models import KbChunk

    count = await db.scalar(
        select(func.count(KbChunk.id)).where(KbChunk.document_id == document_id)
    )
    return int(count or 0)


def _document_is_inflight_without_chunks(doc) -> bool:
    """A zero-chunk duplicate should reuse only genuinely in-flight work."""
    active_statuses = {"pending", "parsing", "indexing", "collecting", "running"}
    return (
        doc.parse_status in active_statuses
        or doc.vector_status in active_statuses
    )


async def _find_content_duplicate(
    db: AsyncSession,
    file,
    owner_id: int,
):
    """Return a same-owner knowledge doc for the same file content when reusable.

    Same-content docs with chunks are canonical and should be reused. Same-content
    docs still in parse/vector startup are also reused to avoid duplicate work.
    Zero-chunk docs that already reached a terminal parse/vector state are treated
    as orphan debt and do not block a fresh ingest.
    """
    from ..models import KbDocument

    md5_hash = getattr(file, "md5_hash", None)
    if not md5_hash:
        return None, None

    result = await db.execute(
        select(KbDocument)
        .join(File, File.id == KbDocument.file_id)
        .where(
            KbDocument.owner_id == owner_id,
            KbDocument.deleted.is_(False),
            File.deleted.is_(False),
            File.md5_hash == md5_hash,
        )
        .order_by(KbDocument.updated_at.desc(), KbDocument.id.desc())
    )
    inflight_doc = None
    for candidate in result.scalars().all():
        chunk_count = await _count_document_chunks(db, int(candidate.id))
        if chunk_count > 0:
            return candidate, {
                "task_id": None,
                "enqueued": False,
                "reason": "content already indexed",
            }
        if inflight_doc is None and _document_is_inflight_without_chunks(candidate):
            inflight_doc = candidate

    if inflight_doc is not None:
        task_info = await enqueue_pipeline_task(db, inflight_doc, owner_id)
        return inflight_doc, task_info

    return None, None


async def register_document(
    db: AsyncSession,
    file_id: int,
    owner_id: int,
    catalog_id: int | None = None,
) -> dict:
    """将框架文件登记为知识库文档。"""
    from ..models import KbDocument

    file = await check_file_access(db, file_id, owner_id)
    ext = (file.extension or "").lower().strip(".")
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValidationError(f"Unsupported file extension: {ext}")

    await db.execute(
        text("SELECT pg_advisory_xact_lock(:owner_id, :file_id)"),
        {"owner_id": owner_id, "file_id": file_id},
    )
    if file.md5_hash:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, ('x' || substr(:md5_hash, 1, 8))::bit(32)::int)"),
            {"namespace": 1262633037, "md5_hash": file.md5_hash},
        )

    # 已登记则返回现有记录
    existing_r = await db.execute(
        select(KbDocument).where(
            KbDocument.file_id == file_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted.is_(False),
        )
    )
    existing = existing_r.scalar_one_or_none()
    if existing:
        if document_pipeline_complete(existing):
            task_info = {
                "task_id": None,
                "enqueued": False,
                "reason": "existing_completed",
            }
        else:
            task_info = await enqueue_pipeline_task(db, existing, owner_id)
            await db.commit()
        return document_registration_payload(existing, task_info)

    duplicate_doc, duplicate_task_info = await _find_content_duplicate(db, file, owner_id)
    if duplicate_doc is not None:
        await db.commit()
        return document_registration_payload(duplicate_doc, duplicate_task_info)

    # Look up existing content package for this file
    content_package_id = None
    try:
        from app.models.content import ContentPackage
        cp_r = await db.execute(
            select(ContentPackage).where(
                ContentPackage.source_file_id == file_id,
                ContentPackage.deleted.is_(False),
            ).order_by(ContentPackage.created_at.desc()).limit(1)
        )
        cp = cp_r.scalar_one_or_none()
        if cp:
            content_package_id = cp.id
        else:
            # No content package exists — trigger content pipeline
            try:
                from app.services.module_registry import call_capability
                caller_str = f"user:{owner_id}"
                pipeline_result = await call_capability("content", "pipeline", {"file_id": file_id}, caller_str)
                if pipeline_result and pipeline_result.get("package_id"):
                    content_package_id = pipeline_result["package_id"]
                elif pipeline_result and isinstance(pipeline_result, dict):
                    pkg_data = pipeline_result.get("data", {})
                    if pkg_data and pkg_data.get("package_id"):
                        content_package_id = pkg_data["package_id"]
            except Exception as e:
                logger.warning("Content pipeline auto-trigger failed for file_id=%d: %s", file_id, e)
    except Exception:
        pass

    doc = KbDocument(
        owner_id=owner_id,
        catalog_id=catalog_id,
        file_id=file_id,
        filename=file.name,
        extension=ext,
        file_size=file.size or 0,
        mime_type=file.mime_type or "",
        content_package_id=content_package_id,
        parse_status="pending",
        vector_status="pending",
        raw_status="pending",
        fusion_status="pending",
    )
    db.add(doc)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing_r = await db.execute(
            select(KbDocument).where(
                KbDocument.file_id == file_id,
                KbDocument.owner_id == owner_id,
                KbDocument.deleted.is_(False),
            )
        )
        existing = existing_r.scalar_one_or_none()
        if existing:
            task_info = await enqueue_pipeline_task(db, existing, owner_id)
            await db.commit()
            return document_registration_payload(existing, task_info)
        raise

    # ── 自动入队 kb_pipeline 后台任务（上传即开始分析） ──
    task_info = await enqueue_pipeline_task(db, doc, owner_id)
    await db.commit()
    await db.refresh(doc)
    logger.info(
        "Auto-enqueued kb_pipeline for document_id=%d file_id=%d task_id=%s enqueued=%s",
        doc.id, file_id, task_info.get("task_id"), task_info.get("enqueued"),
    )

    return document_registration_payload(doc, task_info)


def document_payload(doc) -> dict:
    """文档 ORM → API payload。"""
    unavailable_reason = document_source_unavailable_reason(doc)
    source_available = unavailable_reason is None
    source_state = "available" if source_available else unavailable_reason
    return {
        "id": doc.id,
        "owner_id": doc.owner_id,
        "catalog_id": doc.catalog_id,
        "file_id": doc.file_id,
        "filename": doc.filename,
        "extension": doc.extension,
        "file_size": doc.file_size,
        "mime_type": doc.mime_type,
        "parse_status": doc.parse_status,
        "parse_error": doc.parse_error,
        "vector_status": doc.vector_status,
        "raw_status": getattr(doc, "raw_status", "pending"),
        "fusion_status": getattr(doc, "fusion_status", "pending"),
        "total_chunks": doc.total_chunks,
        "total_pages": doc.total_pages,
        "summary": doc.summary,
        "content_package_id": doc.content_package_id if hasattr(doc, "content_package_id") else None,
        "source_available": source_available,
        "source_state": source_state,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def document_registration_payload(doc, task_info: dict | None = None) -> dict:
    """Document payload plus stable ingest queue metadata."""
    payload = document_payload(doc)
    info = task_info or {
        "task_id": None,
        "enqueued": False,
        "reason": "not_enqueued",
    }
    enqueued = bool(info.get("enqueued"))
    reason = str(info.get("reason") or "")
    unavailable_reason = document_source_unavailable_reason(doc)
    source_available = unavailable_reason is None
    if not source_available:
        status = "source_unavailable"
    elif enqueued:
        status = "queued"
    elif reason == "already_in_flight":
        status = "inflight"
    elif reason == "existing_completed":
        status = "completed"
    else:
        status = "existing"
    search_ready = (
        source_available
        and document_parse_allows_search(doc)
        and doc.vector_status == "done"
        and (doc.total_chunks or 0) > 0
    )
    deep_ready = (
        source_available
        and getattr(doc, "raw_status", "pending") == "done"
        and getattr(doc, "fusion_status", "pending") == "done"
    )
    payload.update({
        "document_id": doc.id,
        "task_id": info.get("task_id"),
        "enqueued": enqueued,
        "reason": reason or None,
        "stage": "source" if not source_available else "kb_pipeline",
        "status": status,
        "pipeline_status": status,
        "search_ready": search_ready,
        "deep_ready": deep_ready,
        "stage_summary": {
            "parse": doc.parse_status,
            "vector": doc.vector_status,
            "raw": getattr(doc, "raw_status", "pending"),
            "fusion": getattr(doc, "fusion_status", "pending"),
        },
    })
    return payload


async def list_documents(
    db: AsyncSession,
    owner_id: int,
    catalog_id: int | None = None,
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """列出知识库文档。"""
    from ..models import KbDocument

    live_conditions = (
        KbDocument.owner_id == owner_id,
        KbDocument.deleted.is_(False),
        File.deleted.is_(False),
    )
    stmt = select(KbDocument).join(File, File.id == KbDocument.file_id).where(*live_conditions)
    count_stmt = select(func.count(KbDocument.id)).join(File, File.id == KbDocument.file_id).where(*live_conditions)
    if catalog_id is not None:
        stmt = stmt.where(KbDocument.catalog_id == catalog_id)
        count_stmt = count_stmt.where(KbDocument.catalog_id == catalog_id)
    if keyword:
        stmt = stmt.where(KbDocument.filename.ilike(f"%{keyword}%"))
        count_stmt = count_stmt.where(KbDocument.filename.ilike(f"%{keyword}%"))

    total = (await db.execute(count_stmt)).scalar() or 0
    offset = (page - 1) * page_size
    r = await db.execute(stmt.order_by(KbDocument.created_at.desc()).offset(offset).limit(page_size))
    docs = r.scalars().all()
    return {
        "items": [document_payload(d) for d in docs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_document(db: AsyncSession, document_id: int, owner_id: int) -> dict:
    """获取文档详情。"""
    from ..models import KbDocument
    from .source_file_state import get_source_file_availability

    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted.is_(False),
        )
    )
    doc = r.scalar_one_or_none()
    if not doc:
        raise NotFound("Document not found")
    source_state = await get_source_file_availability(db, int(doc.file_id or 0))
    if not source_state.available:
        mark_document_source_unavailable(doc, source_state.reason)
        await db.commit()
        raise NotFound(f"Document source file unavailable: {source_state.reason}")
    return document_payload(doc)


async def soft_delete_document(db: AsyncSession, document_id: int, owner_id: int) -> bool:
    """软删除知识库文档。"""
    from ..models import KbDocument

    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted.is_(False),
        )
    )
    doc = r.scalar_one_or_none()
    if not doc:
        raise NotFound("Document not found")
    doc.deleted = True
    await db.commit()
    return True


async def create_page_fusions(db: AsyncSession, document_id: int, owner_id: int, blocks: list[dict]) -> int:
    """按页聚合内容并写入 kb_page_fusions。"""
    from ..models import KbPageFusion

    page_texts: dict[int, list[str]] = {}
    for block in blocks:
        page = block.get("page") or 1
        text = (block.get("text") or "").strip()
        if not text:
            continue
        page_texts.setdefault(page, []).append(text)

    count = 0
    for page, texts in page_texts.items():
        combined = "\n\n".join(texts)
        # 小页直接拼接，大页用 LLM 融合（失败自动回退）
        fused = await fuse_page_text(combined) if len(combined) > 1000 else combined
        pf = KbPageFusion(
            document_id=document_id,
            owner_id=owner_id,
            page=page,
            fused_text=fused,
        )
        db.add(pf)
        count += 1
    await db.commit()
    return count


async def parse_and_index_document(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    caller: str,
    extract_graph: bool = False,
) -> dict:
    """解析 + 分块 + 向量化 + 页级融合 + 可选图谱抽取。

    注意：实体/图谱抽取建议通过后台任务 kb_pipeline 完成（process_document_entities_from_fusions），
    本方法仅提供基础的解析/分块/向量化能力。extract_graph 默认为 False。
    """
    from ..models import KbChunk, KbDocument, KbPageFusion

    # 查询文档并抢占任务状态，防多 worker 重复处理
    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted.is_(False),
        )
    )
    doc = r.scalar_one_or_none()
    if not doc:
        raise NotFound("Document not found")

    if doc.parse_status == "parsing":
        raise AppException("Document is already parsing", status_code=409)

    # 清理旧解析产物（重新解析）
    await db.execute(sa_delete(KbChunk).where(KbChunk.document_id == document_id))
    await db.execute(sa_delete(KbPageFusion).where(KbPageFusion.document_id == document_id))

    doc.parse_status = "parsing"
    doc.vector_status = "pending"
    doc.parse_error = None
    doc.parse_worker_id = f"user:{owner_id}"
    doc.parse_started_at = datetime.now(timezone.utc)
    await db.commit()

    try:
        # First try to get blocks from Content Package (framework canonical source)
        blocks = []
        content_package_id = getattr(doc, "content_package_id", None)
        if content_package_id:
            try:
                from app.models.content import ContentPackageVersion
                cpv_r = await db.execute(
                    select(ContentPackageVersion).where(
                        ContentPackageVersion.package_id == content_package_id,
                    ).order_by(ContentPackageVersion.version_no.desc()).limit(1)
                )
                cpv = cpv_r.scalar_one_or_none()
                if cpv and cpv.content_json:
                    import json
                    content_ir = json.loads(cpv.content_json)

                    def _flatten_cp_blocks(node_list: list[dict], page: int | None = None):
                        result = []
                        for b in node_list:
                            bt = b.get("type", "paragraph")
                            legacy_type = bt
                            if bt == "heading":
                                legacy_type = "标题"
                            elif bt == "paragraph":
                                legacy_type = "段落"
                            elif bt == "table":
                                legacy_type = "表格"
                            elif bt == "image":
                                legacy_type = "图片"
                            elif bt == "code":
                                legacy_type = "代码"
                            result.append({
                                "type": legacy_type,
                                "text": b.get("text", ""),
                                "page": b.get("page") or page,
                                "resource_ref": None,
                                "block_id": b.get("id"),
                            })
                            if b.get("children"):
                                result.extend(_flatten_cp_blocks(
                                    b["children"],
                                    page=b.get("page") or page,
                                ))
                        return result

                    raw_blocks = content_ir.get("blocks", [])
                    blocks = _flatten_cp_blocks(raw_blocks)
            except Exception as e:
                logger.warning("Failed to read from Content Package document_id=%d: %s", document_id, e)

        ir_parse_status = "ok"
        ir_resource_diagnostics: list[dict] = []
        if not blocks:
            parsed_ir = await parse_document(doc.file_id, doc.extension, caller)
            ir_parse_status = parsed_ir.parse_status
            ir_resource_diagnostics = list(parsed_ir.resource_diagnostics)
            parsed = to_legacy_dict(parsed_ir)
            blocks = parsed.get("blocks", [])

        if not blocks:
            reason = PARSER_NO_CONTENT_MARKER
            if "parsed_ir" in locals() and parsed_ir.parse_errors:
                reason = f"{reason}: {', '.join(parsed_ir.parse_errors)}"
            doc.parse_status = "degraded"
            doc.vector_status = "pending"
            doc.total_chunks = 0
            doc.parse_error = reason[:2000]
            await db.commit()
            await db.refresh(doc)
            logger.warning(
                "Parser produced no content for document_id=%d; continuing deep pipeline as degraded: %s",
                document_id,
                reason,
            )
            return {
                "document": document_payload(doc),
                "parsed_blocks": 0,
                "stored_chunks": 0,
                "total_pages": doc.total_pages or 1,
                "status": "degraded",
                "reason": reason,
                "ir_parse_status": ir_parse_status,
                "ir_resource_diagnostics": ir_resource_diagnostics,
            }

        # 写页级融合
        total_pages = await create_page_fusions(db, document_id, owner_id, blocks)

        # 分块 + 向量化
        doc.vector_status = "indexing"
        doc.vector_started_at = datetime.now(timezone.utc)
        await db.commit()

        chunks = await chunk_and_embed(document_id, owner_id, blocks, caller)
        chunk_count = await store_chunks(db, chunks)

        # 可选图谱抽取
        entity_stats = {"entities_found": 0, "relationships_found": 0, "errors": []}
        if extract_graph:
            try:
                entity_stats = await process_document_entities(db, document_id, owner_id, blocks)
            except Exception as e:
                logger.warning("Graph extraction failed for document_id=%d (non-fatal): %s", document_id, e)

        # 更新文档状态：优先使用 IR parse_status，当 IR 标记为 ok 时才标 done
        await db.refresh(doc)
        if ir_parse_status in ("degraded", "failed"):
            doc.parse_status = ir_parse_status
        else:
            doc.parse_status = "done"
        doc.vector_status = "done" if chunk_count > 0 else "error"
        doc.total_chunks = chunk_count
        doc.total_pages = total_pages
        await db.commit()
        await db.refresh(doc)

        return {
            "document": document_payload(doc),
            "parsed_blocks": len(blocks),
            "stored_chunks": chunk_count,
            "total_pages": total_pages,
            "entity_stats": entity_stats,
            "ir_parse_status": ir_parse_status,
            "ir_resource_diagnostics": ir_resource_diagnostics,
        }
    except Exception as e:
        await db.refresh(doc)
        doc.parse_status = "error"
        doc.vector_status = "error"
        doc.parse_error = str(e)[:2000]
        await db.commit()
        logger.error("parse_and_index_document failed document_id=%d: %s", document_id, e)
        raise
