"""知识库全链路管道 — 转发到 PipelineOrchestrator。

保留此文件作为 `register_task_handler("kb_pipeline", _pipeline_handler)` 的导入入口。
实际调度逻辑移至 ``pipeline_orchestrator.py``。
"""
import logging

from app.database import AsyncSessionLocal
from app.services.task_worker import register_task_handler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbDocument
from .document_service import (
    document_parse_allows_search,
    mark_document_source_unavailable,
    parse_and_index_document,
)
from .pipeline_orchestrator import run_pipeline as _run_orchestrated
from .source_file_state import get_source_file_availability, raise_if_source_unavailable

logger = logging.getLogger("v2.knowledge").getChild("pipeline")


async def _run_pipeline(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    file_id: int,
    user_id: int,
    force_raw: bool = False,
    force_fusion: bool = False,
) -> dict:
    """委托给 PipelineOrchestrator。"""
    doc = await db.scalar(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted.is_(False),
        )
    )
    if not doc:
        return {"error": f"Document {document_id} not found", "status": "failed"}

    source_file_id = int(doc.file_id or file_id)
    source_state = await get_source_file_availability(db, source_file_id)
    if not source_state.available:
        mark_document_source_unavailable(doc, source_state.reason)
        await db.commit()
        logger.info(
            "Pipeline skipped before parse/index for document_id=%d file_id=%d: %s",
            document_id,
            source_file_id,
            source_state.reason,
        )
        return {
            "document_id": document_id,
            "file_id": source_file_id,
            "status": "skipped",
            "reason": source_state.reason,
            "classification": "source_unavailable",
        }

    if doc and (not document_parse_allows_search(doc) or doc.vector_status != "done"):
        await parse_and_index_document(
            db,
            document_id=document_id,
            owner_id=owner_id,
            caller=f"user:{user_id}",
            extract_graph=False,
        )
    return await _run_orchestrated(
        db, document_id, owner_id, source_file_id, user_id,
        force_raw=force_raw, force_fusion=force_fusion,
    )


async def _pipeline_handler(params: dict) -> dict:
    """框架后台任务 handler：处理 kb_pipeline 任务。

    参数: {"document_id": int, "user_id": int,
           "force_raw": bool, "force_fusion": bool}
    """
    document_id = int(params.get("document_id", 0))
    user_id = int(params.get("user_id", 0)) or 1
    if document_id <= 0:
        return {"error": "document_id required", "status": "failed"}

    async with AsyncSessionLocal() as db:
        df = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
        doc = df.scalar_one_or_none()
        if not doc:
            logger.info("Pipeline task obsolete for missing document_id=%d", document_id)
            return {
                "document_id": document_id,
                "status": "skipped",
                "reason": "doc_missing",
                "classification": "obsolete",
            }
        if doc.deleted:
            logger.info("Pipeline task obsolete for deleted document_id=%d", document_id)
            return {
                "document_id": document_id,
                "file_id": doc.file_id,
                "status": "skipped",
                "reason": "doc_deleted",
                "classification": "obsolete",
            }

        try:
            await raise_if_source_unavailable(db, doc.file_id)
            result = await _run_pipeline(
                db, document_id, doc.owner_id, doc.file_id, user_id,
                force_raw=params.get("force_raw", False),
                force_fusion=params.get("force_fusion", False),
            )
            if result.get("error") and result.get("status") not in {"skipped", "degraded"}:
                return {"status": "failed", **result}
            if result.get("status") == "failed":
                return result
            if result.get("status") == "degraded":
                return {"task_status": "completed", **result}
            if result.get("status") == "skipped":
                return result
            return {"status": "done", **result}
        except Exception as e:
            source_state = await get_source_file_availability(db, doc.file_id)
            if not source_state.available:
                mark_document_source_unavailable(doc, source_state.reason)
                await db.commit()
                logger.info(
                    "Pipeline skipped for document_id=%d file_id=%d: %s",
                    document_id, doc.file_id, source_state.reason,
                )
                return {
                    "document_id": document_id,
                    "file_id": doc.file_id,
                    "status": "skipped",
                    "reason": source_state.reason,
                }
            logger.error("Pipeline handler failed for document_id=%d: %s", document_id, e)
            return {"error": str(e), "status": "failed"}


register_task_handler("kb_pipeline", _pipeline_handler)
