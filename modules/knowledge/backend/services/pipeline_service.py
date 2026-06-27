"""知识库全链路管道（后台任务 kb_pipeline）。

按 采集→融合→画像→图谱→关联 顺序串行，每步落状态。
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.task_worker import register_task_handler

from ..models import KbDocument
from .raw_collection_service import collect_raw_data
from .fusion_service import fuse_all_pages
from .profile_service import generate_document_profile
from .entity_service import process_document_entities_from_fusions
from .relation_service import compute_file_relations

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
    """按顺序执行全链路，每步完成后 commit 状态。

    返回每步结果汇总。
    """
    steps: dict[str, dict] = {}

    # 第1步：原始采集
    logger.info("Pipeline step 1/5: raw collection doc_id=%d", document_id)
    if doc := (await db.execute(select(KbDocument).where(KbDocument.id == document_id))).scalar_one_or_none():
        if doc.raw_status != "done" or force_raw:
            try:
                steps["raw"] = await collect_raw_data(db, document_id, owner_id, file_id, user_id)
                await db.commit()
                logger.info("Pipeline raw collection done: %d rounds", len(steps["raw"].get("rounds", [])))
            except Exception as e:
                steps["raw"] = {"error": str(e)}
                logger.error("Pipeline raw collection failed: %s", e)
        else:
            steps["raw"] = {"status": "skipped", "reason": "already done"}
    else:
        return {"error": f"Document {document_id} not found"}

    # Y3/Y6: 前步失败则短路，不继续跑后续步骤
    raw_step = steps.get("raw", {})
    if "error" in raw_step or raw_step.get("status") == "failed":
        logger.error("Pipeline aborted after step 1 (raw collection failed) for doc_id=%d", document_id)
        doc.raw_status = "failed"
        await db.commit()
        return {"document_id": document_id, "status": "failed", "steps": steps}

    # 第2步：融合（固化数据，done 则跳过）
    logger.info("Pipeline step 2/5: fusion doc_id=%d", document_id)
    if doc.fusion_status != "done" or force_fusion:
        try:
            steps["fusion"] = await fuse_all_pages(db, document_id, owner_id)
            await db.commit()
        except Exception as e:
            steps["fusion"] = {"error": str(e)}
            logger.error("Pipeline fusion failed: %s", e)
    else:
        steps["fusion"] = {"status": "skipped", "reason": "already done"}

    # Y6: 融合失败则短路，不跑画像/图谱
    if "error" in steps.get("fusion", {}):
        logger.error("Pipeline aborted after step 2 (fusion failed) for doc_id=%d", document_id)
        return {"document_id": document_id, "status": "failed", "steps": steps}

    # 第3步：画像（LLM 分析层，始终重跑——模型升级后可能产出更好结果）
    logger.info("Pipeline step 3/5: profile doc_id=%d", document_id)
    try:
        steps["profile"] = await generate_document_profile(db, document_id, owner_id)
        await db.commit()
    except Exception as e:
        steps["profile"] = {"error": str(e)}
        logger.error("Pipeline profile failed: %s", e)

    # 第4步：图谱（LLM 分析层，始终重跑）
    logger.info("Pipeline step 4/5: graph doc_id=%d", document_id)
    try:
        steps["graph"] = await process_document_entities_from_fusions(db, document_id, owner_id)
        await db.commit()
    except Exception as e:
        steps["graph"] = {"error": str(e)}
        logger.error("Pipeline graph failed: %s", e)

    # 第5步：跨文件关联（依赖图谱+画像，始终重跑但内部幂等）
    logger.info("Pipeline step 5/5: relations doc_id=%d", document_id)
    try:
        steps["relations"] = await compute_file_relations(db, document_id, owner_id)
        await db.commit()
    except Exception as e:
        steps["relations"] = {"error": str(e)}
        logger.error("Pipeline relations failed: %s", e)

    # 汇总结果
    has_errors = any("error" in s for s in steps.values())
    status = "done_with_errors" if has_errors else "done"
    return {"document_id": document_id, "status": status, "steps": steps}


# ── 框架任务 handler ────────────────────────────────


async def _pipeline_handler(params: dict) -> dict:
    """框架后台任务 handler：处理 kb_pipeline 任务。

    参数: {"document_id": int, "user_id": int}
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
