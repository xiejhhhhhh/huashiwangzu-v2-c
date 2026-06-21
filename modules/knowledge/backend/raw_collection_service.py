"""原始层多轮采集服务。

对文档每页执行三轮独立采集（文本提取 / 截图OCR / 视觉构成），
每轮结果各自落盘到 kb_raw_data，落盘后只读不可变。

并发策略：5 门池摊平任务。将所有 (page, round) 摊平成独立任务，
固定 5 并发门池跑，每任务独立 DB 会话 + 独立 commit，
进度三行各自按真实速度前进。
"""
import asyncio
import hashlib
import logging

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.task_worker import register_task_handler

from .models import KbDocument, KbRawData
from .parsing_service import parse_document
from .pdf_render_service import render_page_to_image, get_pdf_page_count

logger = logging.getLogger("v2.knowledge.raw_collection")

# 并发上限对齐 gate_pool.PER_GATE_MAX_CONCURRENT=5
RAW_COLLECT_CONCURRENCY = 5

ROUND_2_OCR_PROMPT = "请识别并提取图片中所有可见的文字内容，包括标题、正文、表格中的文字等。按原顺序输出。"
ROUND_3_VISION_PROMPT = "请详细描述这张页面的版面和视觉构成，包括：1)整体布局结构 2)图表/图片的位置和内容 3)色彩和视觉层次 4)任何特殊视觉元素。"


def _hash_content(content: str) -> str:
    return hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()


async def _exec_round_1_text(
    doc_id: int, file_id: int, owner_id: int,
    page: int, caller: str,
) -> dict:
    """第1轮：文本提取。独立 DB 会话，单独 commit。"""
    async with AsyncSessionLocal() as task_db:
        try:
            parsed = await parse_document(file_id, "pdf", caller)
            blocks = parsed.get("blocks", [])
            page_texts = [
                (b.get("text") or "").strip()
                for b in blocks
                if b.get("page") == page and (b.get("text") or "").strip()
            ]
            content = "\n\n".join(page_texts)
        except Exception as e:
            logger.warning("Round 1 text extraction failed for doc_id=%d page=%d: %s", doc_id, page, e)
            content = ""

        record = KbRawData(
            document_id=doc_id,
            file_id=file_id,
            owner_id=owner_id,
            page=page,
            round=1,
            source_type="text",
            content=content,
            model_used="deepseek-v4-flash" if "pdf" in str(caller).lower() else "parser",
            confidence=0.95 if content else 0.0,
            content_hash=_hash_content(content),
        )
        task_db.add(record)
        await task_db.commit()
        logger.info("Raw collection round=1 page=%d done (%d chars)", page, len(content))
        return {"round": 1, "page": page, "chars": len(content)}


async def _exec_round_2_ocr(
    doc_id: int, file_id: int, owner_id: int,
    page: int, user_id: int,
    img_bytes: bytes | None = None,
) -> dict:
    """第2轮：截图 OCR。独立 DB 会话，单独 commit。"""
    from app.services.model_services import describe_image

    async with AsyncSessionLocal() as task_db:
        try:
            if img_bytes is None:
                img_bytes = await render_page_to_image(file_id, page, user_id)
            content = await describe_image(
                img_bytes,
                prompt=ROUND_2_OCR_PROMPT,
                mime_type="image/png",
                profile_key="mimo",
            )
        except Exception as e:
            logger.warning("Round 2 OCR failed for doc_id=%d page=%d: %s", doc_id, page, e)
            content = ""

        record = KbRawData(
            document_id=doc_id,
            file_id=file_id,
            owner_id=owner_id,
            page=page,
            round=2,
            source_type="ocr",
            content=content,
            model_used="mimo-v2.5",
            confidence=0.85 if content else 0.0,
            content_hash=_hash_content(content),
            metadata_json={"method": "vlm_ocr", "provider": "mimo"},
        )
        task_db.add(record)
        await task_db.commit()
        logger.info("Raw collection round=2 page=%d done (%d chars)", page, len(content))
        return {"round": 2, "page": page, "chars": len(content)}


async def _exec_round_3_vision(
    doc_id: int, file_id: int, owner_id: int,
    page: int, user_id: int,
    img_bytes: bytes | None = None,
) -> dict:
    """第3轮：视觉构成。独立 DB 会话，单独 commit。"""
    from app.services.model_services import describe_image

    async with AsyncSessionLocal() as task_db:
        try:
            if img_bytes is None:
                img_bytes = await render_page_to_image(file_id, page, user_id)
            content = await describe_image(
                img_bytes,
                prompt=ROUND_3_VISION_PROMPT,
                mime_type="image/png",
                profile_key="mimo",
            )
        except Exception as e:
            logger.warning("Round 3 vision failed for doc_id=%d page=%d: %s", doc_id, page, e)
            content = ""

        record = KbRawData(
            document_id=doc_id,
            file_id=file_id,
            owner_id=owner_id,
            page=page,
            round=3,
            source_type="vision",
            content=content,
            model_used="mimo-v2.5",
            confidence=0.80 if content else 0.0,
            content_hash=_hash_content(content),
            metadata_json={"method": "vlm_vision", "provider": "mimo"},
        )
        task_db.add(record)
        await task_db.commit()
        logger.info("Raw collection round=3 page=%d done (%d chars)", page, len(content))
        return {"round": 3, "page": page, "chars": len(content)}


async def _pre_render_pages(file_id: int, user_id: int, total_pages: int) -> dict[int, bytes]:
    """预渲染所有 PDF 页面为图片字节（仅一次，round2/round3 共享）。"""
    images: dict[int, bytes] = {}
    for page in range(1, total_pages + 1):
        try:
            images[page] = await render_page_to_image(file_id, page, user_id)
        except Exception as e:
            logger.warning("Pre-render page=%d failed: %s", page, e)
    return images


async def collect_raw_data(db: AsyncSession, doc_id: int, owner_id: int, file_id: int, user_id: int) -> dict:
    """对文档所有页执行三轮并行采集，落盘 kb_raw_data。

    使用 5 并发门池摊平所有 (page, round) 任务，
    每任务独立 DB 会话 + 独立 commit，
    进度三行各自按真实速度前进。

    返回: {"document_id": int, "total_pages": int, "rounds": [...每个任务的结果...], "status": "done"}
    """
    caller = f"user:{user_id}"

    # 确定页数
    df = await db.execute(select(KbDocument).where(KbDocument.id == doc_id))
    doc = df.scalar_one_or_none()
    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    ext = (doc.extension or "").lower()
    is_pdf = ext == "pdf"

    if is_pdf:
        try:
            total_pages = await get_pdf_page_count(file_id, user_id)
        except Exception:
            total_pages = doc.total_pages or 1
    else:
        total_pages = doc.total_pages or 1

    # 更新文档状态
    doc.raw_status = "collecting"
    doc.total_pages = total_pages
    await db.commit()

    # 已完成页跳过 → 幂等可重入
    dr = await db.execute(
        select(KbRawData.page).where(KbRawData.document_id == doc_id)
    )
    page_round_count: dict[int, int] = {}
    for (pg,) in dr.all():
        page_round_count[pg] = page_round_count.get(pg, 0) + 1
    expected_rounds = 3 if is_pdf else 2
    done_pages = {pg for pg, cnt in page_round_count.items() if cnt >= expected_rounds}

    # 清除未完成页的残缺旧记录
    for page in range(1, total_pages + 1):
        if page not in done_pages:
            async with AsyncSessionLocal() as clean_db:
                await clean_db.execute(
                    sa_delete(KbRawData).where(
                        KbRawData.document_id == doc_id, KbRawData.page == page
                    )
                )
                await clean_db.commit()

    # 预渲染页面图片（只一次，OCR 与视觉共用）
    page_images: dict[int, bytes] = {}
    if is_pdf:
        page_images = await _pre_render_pages(file_id, user_id, total_pages)
    else:
        # 图片文件：读原始字节一次
        from pathlib import Path
        from app.config import get_settings
        from app.services.file_service import check_file_access as _check_fa
        try:
            async with AsyncSessionLocal() as fdb:
                f_rec = await _check_fa(fdb, file_id, user_id)
            img_path = Path(get_settings().UPLOAD_DIR).resolve() / f_rec.storage_path
            img_bytes = img_path.read_bytes()
            for page in range(1, total_pages + 1):
                page_images[page] = img_bytes
        except Exception as e:
            logger.warning("Cannot read image bytes for file_id=%d: %s", file_id, e)

    # 5 并发门池 + 摊平任务列表
    sem = asyncio.Semaphore(RAW_COLLECT_CONCURRENCY)
    all_results: list[dict] = []

    async def _task_wrapper(round_num: int, page: int) -> dict:
        async with sem:
            if round_num == 1:
                return await _exec_round_1_text(doc_id, file_id, owner_id, page, caller)
            elif round_num == 2:
                return await _exec_round_2_ocr(doc_id, file_id, owner_id, page, user_id, img_bytes=page_images.get(page))
            elif round_num == 3:
                return await _exec_round_3_vision(doc_id, file_id, owner_id, page, user_id, img_bytes=page_images.get(page))
            return {"round": round_num, "page": page, "error": "unknown round"}

    tasks = []
    for page in range(1, total_pages + 1):
        if page in done_pages:
            logger.info("Raw collection page=%d already done, skip", page)
            continue
        tasks.append(_task_wrapper(1, page))
        tasks.append(_task_wrapper(2, page))
        tasks.append(_task_wrapper(3, page))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.warning("Round task failed: %s", r)
            else:
                all_results.append(r)

    await db.refresh(doc)
    doc.raw_status = "done"
    await db.commit()

    return {
        "document_id": doc_id,
        "total_pages": total_pages,
        "rounds": all_results,
        "status": "done",
    }


async def get_raw_data(
    db: AsyncSession, document_id: int, page: int | None = None,
    round_num: int | None = None,
) -> list[dict]:
    """查询原始采集数据。

    返回: [{"id": int, "page": int, "round": int, "source_type": str, "content": str, ...}, ...]
    """
    stmt = select(KbRawData).where(KbRawData.document_id == document_id)
    if page is not None:
        stmt = stmt.where(KbRawData.page == page)
    if round_num is not None:
        stmt = stmt.where(KbRawData.round == round_num)
    stmt = stmt.order_by(KbRawData.page, KbRawData.round)

    r = await db.execute(stmt)
    records = r.scalars().all()
    return [
        {
            "id": rec.id,
            "page": rec.page,
            "round": rec.round,
            "source_type": rec.source_type,
            "content": rec.content,
            "model_used": rec.model_used,
            "confidence": rec.confidence,
            "content_hash": rec.content_hash,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        }
        for rec in records
    ]


# ── 框架任务 handler ────────────────────────────────
async def _raw_collection_handler(params: dict) -> dict:
    """框架后台任务 handler：处理 kb_collect_raw 任务。"""
    document_id = int(params.get("document_id", 0))
    if document_id <= 0:
        return {"error": "document_id required", "status": "failed"}

    async with AsyncSessionLocal() as db:
        df = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
        doc = df.scalar_one_or_none()
        if not doc:
            return {"error": f"Document {document_id} not found", "status": "failed"}

        try:
            result = await collect_raw_data(db, document_id, doc.owner_id, doc.file_id, doc.owner_id)
            return {"status": "done", **result}
        except Exception as e:
            logger.error("Raw collection failed for document_id=%d: %s", document_id, e)
            doc.raw_status = "failed"
            await db.commit()
            return {"error": str(e), "status": "failed"}


# 注册到框架任务队列
register_task_handler("kb_collect_raw", _raw_collection_handler)
