"""知识库文档管理服务：资料登记、解析入库、页级融合、索引状态。"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, delete as sa_delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound, ValidationError, AppException
from app.services.file_service import check_file_access

from .parsing_service import parse_document
from .embedding_service import chunk_and_embed, store_chunks
from .entity_service import process_document_entities, fuse_page_text

logger = logging.getLogger("v2.knowledge.document")

SUPPORTED_EXTENSIONS = {
    "pdf", "docx", "pptx", "xlsx", "csv", "txt", "md",
    "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg",
}


def resolve_user_id(caller: str) -> int:
    """caller: user:{id} → int user_id。"""
    from app.core.exceptions import PermissionDenied

    try:
        prefix, raw_id = caller.split(":", 1)
        if prefix == "user":
            return int(raw_id)
    except (TypeError, ValueError):
        pass
    raise PermissionDenied("Invalid caller")


async def register_document(
    db: AsyncSession,
    file_id: int,
    owner_id: int,
    catalog_id: int | None = None,
) -> dict:
    """将框架文件登记为知识库文档。"""
    from .models import KbDocument

    file = await check_file_access(db, file_id, owner_id)
    ext = (file.extension or "").lower().strip(".")
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValidationError(f"Unsupported file extension: {ext}")

    # 已登记则返回现有记录
    existing_r = await db.execute(
        select(KbDocument).where(
            KbDocument.file_id == file_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted == False,
        )
    )
    existing = existing_r.scalar_one_or_none()
    if existing:
        return document_payload(existing)

    doc = KbDocument(
        owner_id=owner_id,
        catalog_id=catalog_id,
        file_id=file_id,
        filename=file.name,
        extension=ext,
        file_size=file.size or 0,
        mime_type=file.mime_type or "",
        parse_status="pending",
        vector_status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return document_payload(doc)


def document_payload(doc) -> dict:
    """文档 ORM → API payload。"""
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
        "total_chunks": doc.total_chunks,
        "total_pages": doc.total_pages,
        "summary": doc.summary,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


async def list_documents(
    db: AsyncSession,
    owner_id: int,
    catalog_id: int | None = None,
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """列出知识库文档。"""
    from .models import KbDocument

    stmt = select(KbDocument).where(KbDocument.owner_id == owner_id, KbDocument.deleted == False)
    count_stmt = select(func.count(KbDocument.id)).where(KbDocument.owner_id == owner_id, KbDocument.deleted == False)
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
    from .models import KbDocument

    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted == False,
        )
    )
    doc = r.scalar_one_or_none()
    if not doc:
        raise NotFound("Document not found")
    return document_payload(doc)


async def soft_delete_document(db: AsyncSession, document_id: int, owner_id: int) -> bool:
    """软删除知识库文档。"""
    from .models import KbDocument

    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted == False,
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
    from .models import KbPageFusion

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
    extract_graph: bool = True,
) -> dict:
    """解析 + 分块 + 向量化 + 页级融合 + 可选图谱抽取。"""
    from .models import KbDocument, KbChunk, KbPageFusion

    # 查询文档并抢占任务状态，防多 worker 重复处理
    r = await db.execute(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted == False,
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
        parsed = await parse_document(doc.file_id, doc.extension, caller)
        blocks = parsed.get("blocks", [])
        if not blocks:
            raise ValidationError("Parser returned no content blocks")

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

        # 更新文档状态
        await db.refresh(doc)
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
        }
    except Exception as e:
        await db.refresh(doc)
        doc.parse_status = "error"
        doc.vector_status = "error"
        doc.parse_error = str(e)[:2000]
        await db.commit()
        logger.error("parse_and_index_document failed document_id=%d: %s", document_id, e)
        raise
