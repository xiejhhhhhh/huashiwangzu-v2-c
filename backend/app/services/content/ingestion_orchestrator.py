"""内容摄取编排器（方案07 §17-§20 / WP2-A）。

职责边界：
- 只负责「唤醒」——把 file.uploaded / 手动重放 / 续跑 翻译成一条 IngestionRun
  + 一条 package_ensure 阶段任务，在同一事务里落库（run + publish_task 原子）。
- 真正的阶段业务在 ingestion_stages.py；调度/租约/重试在 task_dispatcher。
- 本轮（§24）越过 LLM/VLM/OCR/ASR/embedding，编排器不感知模型，纯发任务。

链路：file.uploaded → ensure_run_and_kickoff → publish(package_ensure)
      → dispatcher 认领 → 阶段 handler 跑一阶段 → settlement 发后继阶段。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.content_runtime import FileRevision
from app.models.file import File
from app.services.content.ingestion_run_store import (
    create_or_get_run,
    create_replay,
    get_run,
)
from app.services.content.source_revision import resolve_source_sha256
from app.services.file_reader import resolve_caller_user_id
from app.services.task_dispatcher import publish_task

logger = logging.getLogger("v2.content").getChild("ingestion.orchestrator")

INGEST_TASK_TYPE = "content_ingest_stage"
ROOT_STAGE = "package_ensure"
PIPELINE_VERSION = "v1"

# 支持进入摄取管线的扩展名（与旧 pipeline SUPPORTED_EXTENSIONS 对齐，1:1 不缩水）。
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
    "csv", "tsv", "txt", "md", "markdown",
    "json", "yaml", "yml",
    "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg",
    "eml", "msg",
})


async def _latest_revision_id(db: AsyncSession, file_id: int) -> int | None:
    """取该文件最新一条 FileRevision.id（上传/替换时已写）。历史文件可能无。"""
    return await db.scalar(
        select(FileRevision.id)
        .where(FileRevision.file_id == file_id)
        .order_by(FileRevision.revision_no.desc(), FileRevision.id.desc())
        .limit(1)
    )


def _stage_body(
    *,
    run_id: str,
    file_id: int,
    package_id: int | None,
    source_revision_id: int | None,
    source_sha256: str | None,
    generation: int,
    stage: str,
) -> dict[str, Any]:
    """冻结的任务 body 契约（§五）。不含物理路径——dispatcher 会拒。"""
    return {
        "run_id": run_id,
        "file_id": file_id,
        "package_id": package_id,
        "source_revision_id": source_revision_id,
        "source_sha256": source_sha256,
        "pipeline_version": PIPELINE_VERSION,
        "generation": generation,
        "stage": stage,
    }


async def _publish_stage(
    db: AsyncSession,
    *,
    run,
    stage: str,
    owner_id: int,
    requested_by: int,
    trigger: str,
    lane_key: str = "local_preprocess",
    priority: int = 0,
) -> None:
    """在调用方事务里发一个阶段任务（flush-only，不 commit）。"""
    body = _stage_body(
        run_id=run.id,
        file_id=run.file_id,
        package_id=run.package_id,
        source_revision_id=run.source_revision_id,
        source_sha256=run.source_sha256,
        generation=run.generation,
        stage=stage,
    )
    # dependency_key 仅作可观测标记（dispatcher 透传，不做去重/门控）。真正防重：
    # 建 run 幂等(create_or_get_run) + settlement 每次成功只发一次后继 + 阶段 handler 幂等。
    dependency_key = f"ingest:{run.id}:{stage}"
    await publish_task(
        db,
        task_type=INGEST_TASK_TYPE,
        module="content",
        owner_id=owner_id,
        body=body,
        requested_by=f"user:{requested_by}" if requested_by else "system:ingest",
        trigger=trigger,
        stage_key=stage,
        lane_key=lane_key,
        dependency_key=dependency_key,
        ready_status="ready",
        priority=priority,
        document_id=run.file_id,
    )


async def ensure_run_and_kickoff(
    file_id: int,
    caller: str,
    *,
    trigger: str = "upload",
) -> dict[str, Any]:
    """file.uploaded 主入口：幂等建 run + 发首阶段任务（一个事务原子落库）。

    幂等：同一字节版本（source_revision_id+pipeline_version+generation）只会有一条 run；
    重复的 file.uploaded 不会重复建 run（唯一键幂等），只有 created=True 才发首阶段。
    """
    async with AsyncSessionLocal() as db:
        caller_user_id = resolve_caller_user_id(caller)
        file_record = await db.get(File, file_id)
        if not file_record or file_record.deleted:
            return {"skipped": True, "reason": "file_not_found", "file_id": file_id}

        ext = (file_record.extension or "").lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return {"skipped": True, "reason": f"unsupported_format:{ext}", "file_id": file_id}

        source_revision_id = await _latest_revision_id(db, file_id)
        source_sha256 = await resolve_source_sha256(db, file_record)

        run, created = await create_or_get_run(
            db,
            file_id=file_id,
            source_revision_id=source_revision_id,
            source_sha256=source_sha256,
            owner_id=file_record.owner_id,
            trigger=trigger,
            requested_by=caller_user_id,
        )

        if not created:
            # 已有 run。终态则不动（要重跑走 replay）；非终态说明管线在途，不重复发首阶段。
            await db.commit()
            return {
                "run_id": run.id,
                "status": run.status,
                "created": False,
                "note": "existing_run",
            }

        await _publish_stage(
            db, run=run, stage=ROOT_STAGE,
            owner_id=file_record.owner_id, requested_by=caller_user_id,
            trigger=trigger,
        )
        await db.commit()
        logger.info(
            "Ingestion kicked off: file_id=%d run_id=%s gen=%d",
            file_id, run.id, run.generation,
        )
        return {"run_id": run.id, "status": run.status, "created": True}


async def replay_run(origin_run_id: str, caller: str) -> dict[str, Any]:
    """重放：基于终态 run 建 generation+1 新 run 并发首阶段。额度恢复后重跑 deferred 用。"""
    async with AsyncSessionLocal() as db:
        caller_user_id = resolve_caller_user_id(caller)
        origin = await get_run(db, origin_run_id)
        if origin is None:
            return {"error": "run_not_found", "run_id": origin_run_id}
        replay = await create_replay(db, origin, requested_by=caller_user_id)
        await _publish_stage(
            db, run=replay, stage=ROOT_STAGE,
            owner_id=replay.owner_id, requested_by=caller_user_id,
            trigger="replay",
        )
        await db.commit()
        logger.info("Ingestion replay: origin=%s new_run=%s gen=%d", origin_run_id, replay.id, replay.generation)
        return {"run_id": replay.id, "status": replay.status, "replay_of": origin_run_id, "generation": replay.generation}
