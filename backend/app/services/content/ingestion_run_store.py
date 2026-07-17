"""IngestionRun 账本读写（方案07 §17/§19.3-B）。

framework_ingestion_runs 是预处理运行账本。规则：
- 唯一键 (source_revision_id, pipeline_version, generation) 保证同一字节版本同一代只有一条 run。
- 终态（completed/degraded/failed/dead_letter/cancelled）不原地重开；replay=新建 generation+1。
- 状态跃迁走乐观锁 lock_version，rowcount=0 视为并发丢失，交由调用方处理。

本模块只做账本 CRUD，不含阶段业务逻辑（那在 ingestion_stages.py）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.ids import new_uuid7
from app.contracts.ingestion_status import INGESTION_TERMINAL_STATES
from app.models.content_runtime import IngestionRun


def _now() -> datetime:
    return datetime.now(timezone.utc)


# 复用 §19.4 冻结的终态集合，避免各处并存多套定义。
TERMINAL_STATUSES: frozenset[str] = INGESTION_TERMINAL_STATES


async def create_or_get_run(
    db: AsyncSession,
    *,
    file_id: int,
    source_revision_id: int | None,
    source_sha256: str | None,
    owner_id: int,
    pipeline_version: str = "v1",
    generation: int = 1,
    trigger: str = "upload",
    requested_by: int = 0,
    package_id: int | None = None,
) -> tuple[IngestionRun, bool]:
    """按唯一键幂等取或建一条 run。返回 (run, created)。flush 不 commit。

    唯一键 (source_revision_id, pipeline_version, generation)。source_revision_id 为空时
    （历史文件无 Revision）退化为按 file_id+pipeline_version+generation 查最近一条，避免每次触发都新建。
    """
    if source_revision_id is not None:
        existing = await db.scalar(
            select(IngestionRun).where(
                IngestionRun.source_revision_id == source_revision_id,
                IngestionRun.pipeline_version == pipeline_version,
                IngestionRun.generation == generation,
            )
        )
    else:
        existing = await db.scalar(
            select(IngestionRun)
            .where(
                IngestionRun.file_id == file_id,
                IngestionRun.source_revision_id.is_(None),
                IngestionRun.pipeline_version == pipeline_version,
                IngestionRun.generation == generation,
            )
            .order_by(IngestionRun.created_at.desc())
            .limit(1)
        )
    if existing is not None:
        return existing, False

    run = IngestionRun(
        id=new_uuid7(),
        file_id=file_id,
        source_revision_id=source_revision_id,
        owner_id=owner_id,
        source_sha256=source_sha256,
        pipeline_version=pipeline_version,
        generation=generation,
        package_id=package_id,
        status="queued",
        trigger=trigger,
        requested_by=requested_by,
        lock_version=0,
    )
    db.add(run)
    await db.flush()
    return run, True


async def get_run(db: AsyncSession, run_id: str) -> IngestionRun | None:
    return await db.get(IngestionRun, run_id)


async def transition(
    db: AsyncSession,
    run_id: str,
    *,
    expected_lock_version: int,
    to_status: str,
    **fields: Any,
) -> bool:
    """乐观锁状态跃迁。命中(rowcount==1)返回 True；并发丢失返回 False。flush 不 commit。

    自动维护 lock_version+1、updated_at；终态自动补 completed_at。
    """
    values: dict[str, Any] = {
        "status": to_status,
        "lock_version": expected_lock_version + 1,
        "updated_at": _now(),
        **fields,
    }
    if to_status in TERMINAL_STATUSES and "completed_at" not in values:
        values["completed_at"] = _now()
    result = await db.execute(
        update(IngestionRun)
        .where(
            IngestionRun.id == run_id,
            IngestionRun.lock_version == expected_lock_version,
        )
        .values(**values)
    )
    return int(result.rowcount or 0) == 1


async def mark_running(db: AsyncSession, run: IngestionRun) -> bool:
    return await transition(
        db, run.id, expected_lock_version=run.lock_version,
        to_status="running",
    )


async def mark_completed(db: AsyncSession, run: IngestionRun, *, package_version_id: int | None = None) -> bool:
    extra: dict[str, Any] = {}
    if package_version_id is not None:
        extra["package_version_id"] = package_version_id
    return await transition(
        db, run.id, expected_lock_version=run.lock_version,
        to_status="completed", **extra,
    )


async def mark_degraded(db: AsyncSession, run: IngestionRun, *, error_code: str | None = None, error_message: str | None = None) -> bool:
    return await transition(
        db, run.id, expected_lock_version=run.lock_version,
        to_status="degraded",
        error_code=error_code, error_message=error_message,
    )


async def mark_failed(db: AsyncSession, run: IngestionRun, *, error_code: str | None = None, error_message: str | None = None) -> bool:
    return await transition(
        db, run.id, expected_lock_version=run.lock_version,
        to_status="failed",
        error_code=error_code, error_message=error_message,
    )


async def request_cancel(db: AsyncSession, run_id: str, *, reason: str = "") -> bool:
    """打取消标记；各阶段 handler 开头检查后主动落 cancelled。flush 不 commit。"""
    result = await db.execute(
        update(IngestionRun)
        .where(
            IngestionRun.id == run_id,
            IngestionRun.status.notin_(tuple(TERMINAL_STATUSES)),
        )
        .values(cancel_requested=True, cancel_reason=(reason or "user_cancel")[:256], updated_at=_now())
    )
    return int(result.rowcount or 0) == 1


async def create_replay(
    db: AsyncSession,
    origin_run: IngestionRun,
    *,
    requested_by: int = 0,
) -> IngestionRun:
    """基于原 run 建 generation+1 的重放 run（终态不原地重开）。flush 不 commit。"""
    replay = IngestionRun(
        id=new_uuid7(),
        file_id=origin_run.file_id,
        source_revision_id=origin_run.source_revision_id,
        owner_id=origin_run.owner_id,
        source_sha256=origin_run.source_sha256,
        pipeline_version=origin_run.pipeline_version,
        generation=origin_run.generation + 1,
        package_id=origin_run.package_id,
        status="queued",
        trigger="replay",
        requested_by=requested_by,
        replay_of_id=origin_run.id,
        lock_version=0,
    )
    db.add(replay)
    await db.flush()
    return replay


def run_to_dict(run: IngestionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "file_id": run.file_id,
        "source_revision_id": run.source_revision_id,
        "owner_id": run.owner_id,
        "source_sha256": run.source_sha256,
        "pipeline_version": run.pipeline_version,
        "generation": run.generation,
        "package_id": run.package_id,
        "package_version_id": run.package_version_id,
        "status": run.status,
        "trigger": run.trigger,
        "replay_of_id": run.replay_of_id,
        "cancel_requested": run.cancel_requested,
        "cancel_reason": run.cancel_reason,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
