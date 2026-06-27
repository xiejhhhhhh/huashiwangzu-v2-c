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
from .pipeline_orchestrator import run_pipeline as _run_orchestrated

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
    return await _run_orchestrated(
        db, document_id, owner_id, file_id, user_id,
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
            return {"error": f"Document {document_id} not found", "status": "failed"}

        try:
            result = await _run_pipeline(
                db, document_id, doc.owner_id, doc.file_id, user_id,
                force_raw=params.get("force_raw", False),
                force_fusion=params.get("force_fusion", False),
            )
            return {"status": "done", **result}
        except Exception as e:
            logger.error("Pipeline handler failed for document_id=%d: %s", document_id, e)
            return {"error": str(e), "status": "failed"}


register_task_handler("kb_pipeline", _pipeline_handler)
