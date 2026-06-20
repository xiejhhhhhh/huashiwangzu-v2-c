"""原始层多轮采集服务。

对文档每页执行三轮独立采集（文本提取 / 截图OCR / 视觉构成），
每轮结果各自落盘到 kb_raw_data，落盘后只读不可变。
"""
import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.task_worker import register_task_handler

from .models import KbDocument, KbRawData
from .parsing_service import parse_document
from .pdf_render_service import render_page_to_image, get_pdf_page_count

logger = logging.getLogger("v2.knowledge.raw_collection")

ROUND_1_TEXT_PROMPT = "提取所有文字"
ROUND_2_OCR_PROMPT = "请识别并提取图片中所有可见的文字内容，包括标题、正文、表格中的文字等。按原顺序输出。"
ROUND_3_VISION_PROMPT = "请详细描述这张页面的版面和视觉构成，包括：1)整体布局结构 2)图表/图片的位置和内容 3)色彩和视觉层次 4)任何特殊视觉元素。"


def _hash_content(content: str) -> str:
    return hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()


async def _collect_round_1_text(
    db: AsyncSession, doc_id: int, file_id: int, owner_id: int,
    page: int, caller: str,
) -> dict:
    """第1轮：文本提取。从 parser blocks 聚合该页文本。"""
    from .models import KbRawData

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
    db.add(record)
    await db.flush()
    return {"round": 1, "page": page, "chars": len(content)}


async def _collect_round_2_ocr(
    db: AsyncSession, doc_id: int, file_id: int, owner_id: int,
    page: int, user_id: int,
    img_bytes: bytes | None = None,
) -> dict:
    """第2轮：截图 OCR。渲染页面 → VLM 识别文字。"""
    from app.services.model_services import describe_image

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
    db.add(record)
    await db.flush()
    return {"round": 2, "page": page, "chars": len(content)}


async def _collect_round_3_vision(
    db: AsyncSession, doc_id: int, file_id: int, owner_id: int,
    page: int, user_id: int,
    img_bytes: bytes | None = None,
) -> dict:
    """第3轮：视觉构成。渲染页面 → VLM 描述版面/图表/视觉元素。"""
    from app.services.model_services import describe_image

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
    db.add(record)
    await db.flush()
    return {"round": 3, "page": page, "chars": len(content)}


async def collect_raw_data(db: AsyncSession, doc_id: int, owner_id: int, file_id: int, user_id: int) -> dict:
    """对文档所有页执行三轮并行采集，落盘 kb_raw_data。

    返回: {"document_id": int, "total_pages": int, "rounds": [...每个页每轮的结果...], "status": "done"}
    """
    from .document_service import resolve_user_id

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

    # 清空旧原始数据（重新采集）
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(KbRawData).where(KbRawData.document_id == doc_id))
    await db.flush()

    all_results = []

    # 逐页并行三轮
    for page in range(1, total_pages + 1):
        tasks = []

        # 第1轮：文本提取（PDF 走 parser，图片/其他走 describe）
        if is_pdf:
            tasks.append(_collect_round_1_text(db, doc_id, file_id, owner_id, page, caller))
        else:
            # 非 PDF：第1轮取 parser 全局文本，第2/3轮对图跑
            tasks.append(_collect_round_1_text(db, doc_id, file_id, owner_id, page, caller))

        if is_pdf:
            tasks.append(_collect_round_2_ocr(db, doc_id, file_id, owner_id, page, user_id))
            tasks.append(_collect_round_3_vision(db, doc_id, file_id, owner_id, page, user_id))
        else:
            # 图片文件：读取原始字节直接跑 VLM（不渲染）
            from pathlib import Path
            from app.config import get_settings
            from app.services.file_service import check_file_access as _check_fa
            try:
                f_rec = await _check_fa(db, file_id, user_id)
                img_path = Path(get_settings().UPLOAD_DIR).resolve() / f_rec.storage_path
                img_bytes = img_path.read_bytes()
                tasks.append(_collect_round_2_ocr(db, doc_id, file_id, owner_id, page, user_id, img_bytes=img_bytes))
                tasks.append(_collect_round_3_vision(db, doc_id, file_id, owner_id, page, user_id, img_bytes=img_bytes))
            except Exception as e:
                logger.warning("Cannot read image bytes for file_id=%d: %s", file_id, e)

        round_results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in round_results:
            if isinstance(r, Exception):
                logger.warning("Round failed for doc_id=%d page=%d: %s", doc_id, page, r)
            else:
                all_results.append(r)

        # 每页间短暂休息，避免打爆 API
        if page < total_pages:
            await asyncio.sleep(0.3)

    await db.commit()

    # 更新状态
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
