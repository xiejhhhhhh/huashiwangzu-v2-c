"""内容摄取（Ingestion）运行账本对外 HTTP 接口（方案07 WP2 组件D）。

这层只做「查 / 取消 / 重放」的薄外壳，真正的账本读写在
app.services.content.ingestion_run_store，真正的重放编排在
app.services.content.ingestion_orchestrator，本文件不含业务逻辑。

铁律：
- 全部接口鉴权（require_permission），并按 owner_id 隔离——用户只能看/操作
  自己 owner_id 名下的 run；越权一律按「找不到」处理（NotFound），不泄露他人 run 存在与否。
- 只读接口用 viewer 权限；取消/重放是写操作用 editor 权限。
- 取消：只对「非终态」run 打取消标记，终态 run 无可取消 → 冲突错误。
- 重放：只允许「终态」run 重放（非终态说明还在途，重放会撞唯一键）→ 冲突错误。

前缀：/api/content/ingestion
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFound
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.content_runtime import IngestionRun
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.content.ingestion_orchestrator import replay_run
from app.services.content.ingestion_run_store import (
    TERMINAL_STATUSES,
    request_cancel,
    run_to_dict,
)

logger = logging.getLogger("v2.content").getChild("ingestion.api")

router = APIRouter(prefix="/api/content/ingestion", tags=["content-ingestion"])

# 分页安全边界：单页最少 1 条、最多 100 条，避免一次拉爆整表。
_最小页大小 = 1
_默认页大小 = 20
_最大页大小 = 100


async def _取本人可见的run(db: AsyncSession, run_id: str, user: User) -> IngestionRun:
    """按 run_id 取一条 run 并校验归属。

    找不到、或不属于当前用户，一律抛 NotFound（不区分「不存在」和「无权」，
    避免通过 404/403 差异探测他人 run 是否存在）。
    """
    run = await db.get(IngestionRun, run_id)
    if run is None or run.owner_id != user.id:
        raise NotFound("Ingestion run not found")
    return run


@router.get("/runs/{run_id}")
async def 查单条运行(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """查单条摄取运行的状态。

    run 不存在或不属于当前用户 → 404。返回 run_to_dict 的完整账本快照。
    """
    run = await _取本人可见的run(db, run_id, user)
    return ApiResponse(data=run_to_dict(run))


@router.get("/runs")
async def 列出运行(
    file_id: int | None = Query(default=None, description="按文件过滤"),
    status: str | None = Query(default=None, description="按状态过滤"),
    page: int = Query(default=1, ge=1, description="页码，从 1 起"),
    page_size: int = Query(
        default=_默认页大小, ge=_最小页大小, le=_最大页大小, description="每页条数"
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """列出当前用户名下的摄取运行，支持按 file_id / status 过滤，按创建时间倒序分页。

    返回 {"items": [...], "total": N, "page": P, "page_size": S}。
    只返回属于当前用户 owner_id 的 run，天然做 owner 隔离。
    """
    # 基础条件：永远锁死 owner_id，任何过滤都在本人可见范围内叠加。
    条件 = [IngestionRun.owner_id == user.id]
    if file_id is not None:
        条件.append(IngestionRun.file_id == file_id)
    if status:
        条件.append(IngestionRun.status == status)

    总数 = await db.scalar(
        select(func.count()).select_from(IngestionRun).where(*条件)
    )
    总数 = int(总数 or 0)

    偏移 = (page - 1) * page_size
    结果 = await db.execute(
        select(IngestionRun)
        .where(*条件)
        .order_by(desc(IngestionRun.created_at), desc(IngestionRun.id))
        .offset(偏移)
        .limit(page_size)
    )
    条目 = [run_to_dict(run) for run in 结果.scalars().all()]

    return ApiResponse(data={
        "items": 条目,
        "total": 总数,
        "page": page,
        "page_size": page_size,
    })


@router.get("/files/{file_id}/latest")
async def 查文件最新运行(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """查某文件在当前用户名下的最新一条摄取运行（按创建时间倒序取一条）。

    该文件在当前用户名下没有任何 run → 404。
    """
    run = await db.scalar(
        select(IngestionRun)
        .where(
            IngestionRun.file_id == file_id,
            IngestionRun.owner_id == user.id,
        )
        .order_by(desc(IngestionRun.created_at), desc(IngestionRun.id))
        .limit(1)
    )
    if run is None:
        raise NotFound("No ingestion run for this file")
    return ApiResponse(data=run_to_dict(run))


@router.post("/runs/{run_id}/cancel")
async def 取消运行(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """给一条在途运行打取消标记（各阶段 handler 检查后主动落 cancelled）。

    - run 不存在或不属于当前用户 → 404。
    - 已是终态（completed/degraded/failed/dead_letter/cancelled）→ 409，无可取消。
    - 成功：request_cancel 打标（flush 不 commit），本层负责 commit。
    """
    run = await _取本人可见的run(db, run_id, user)
    if run.status in TERMINAL_STATUSES:
        raise ConflictError(
            f"Run is already terminal ({run.status}); nothing to cancel"
        )

    标记成功 = await request_cancel(db, run_id, reason=f"user:{user.id}")
    if not 标记成功:
        # rowcount=0：并发下 run 刚跳到终态，取消标记没打上。
        await db.rollback()
        raise ConflictError(
            "Run reached a terminal state before cancel could be applied"
        )
    await db.commit()
    logger.info("Ingestion cancel requested: run_id=%s by user=%d", run_id, user.id)
    return ApiResponse(data={
        "run_id": run_id,
        "cancel_requested": True,
    })


@router.post("/runs/{run_id}/replay")
async def 重放运行(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    """重放一条终态运行：基于原 run 建 generation+1 新 run 并发首阶段任务。

    - run 不存在或不属于当前用户 → 404。
    - 非终态 run → 409（还在途，重放会撞 (source_revision_id,pipeline_version,generation) 唯一键）。
    - 成功：调 orchestrator.replay_run（自己开 session + commit），返回新 run 信息。

    注意：先用本层 session 做 owner + 终态校验，通过后再交给 orchestrator 用它自己的
    session 落库，两个 session 不共享事务，符合 orchestrator「自管事务」的契约。
    """
    run = await _取本人可见的run(db, run_id, user)
    if run.status not in TERMINAL_STATUSES:
        raise ConflictError(
            f"Only terminal runs can be replayed; current status is '{run.status}'"
        )

    结果 = await replay_run(run_id, f"user:{user.id}")
    # orchestrator 用错误码字典表达「找不到原 run」——正常路径已校验过，
    # 这里兜并发（原 run 在校验后被删）→ 转成 404。
    if isinstance(结果, dict) and 结果.get("error"):
        raise NotFound("Ingestion run not found")
    logger.info("Ingestion replay requested: origin=%s by user=%d", run_id, user.id)
    return ApiResponse(data=结果)
