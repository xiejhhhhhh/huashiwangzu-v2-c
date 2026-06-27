"""知识库 Pipeline 统一引擎（取代 _run_pipeline 的硬编码 5 步）。

设计：
- Stage 注册表：每个 stage 定义名称、依赖、是否始终执行、执行函数
- 统一调度：按注册表顺序迭代，检查 stale/force/状态决定是否跳过
- Hash 追踪：每步完成后记录 artifact hash，下次检测上游变化
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbDocument
from .entity_service import process_document_entities_from_fusions
from .fusion_service import fuse_all_pages
from .profile_service import generate_document_profile
from .raw_collection_service import collect_raw_data
from .relation_service import compute_file_relations
from .stale_tracker import (
    detect_stale_stages,
    mark_stale,
    record_artifact_hash,
)

logger = logging.getLogger("v2.knowledge").getChild("orchestrator")

StageFn = Callable[..., Awaitable[dict]]


@dataclass
class StageDef:
    """单个 pipeline stage 定义。"""
    name: str
    deps: list[str]            # 依赖的上游 stage
    always_run: bool           # True = 每次 pipeline 都执行（不受 stale 影响）
    fn: StageFn                # 异步执行函数
    requires: list[str] = field(default_factory=list)  # 必须前置执行完的 stage


# ── Stage 注册表 ──────────────────────────────────────
# 顺序即执行顺序
STAGE_REGISTRY: list[StageDef] = [
    StageDef(
        name="raw", deps=["source_file"], always_run=False,
        fn=collect_raw_data, requires=[],
    ),
    StageDef(
        name="fusion", deps=["raw"], always_run=False,
        fn=fuse_all_pages, requires=["raw"],
    ),
    StageDef(
        name="profile", deps=["fusion"], always_run=True,
        fn=generate_document_profile, requires=["fusion"],
    ),
    StageDef(
        name="graph", deps=["fusion"], always_run=True,
        fn=process_document_entities_from_fusions, requires=["fusion"],
    ),
    StageDef(
        name="relations", deps=["profile", "graph"], always_run=True,
        fn=compute_file_relations, requires=["profile", "graph"],
    ),
]


async def run_pipeline(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    file_id: int,
    user_id: int,
    force_raw: bool = False,
    force_fusion: bool = False,
) -> dict:
    """统一 pipeline 入口。

    1. 检测 source_file hash 变化 → BFS 传播 stale
    2. force_raw/force_fusion 等价于手动标记对应 stage 为 stale
    3. 按 STAGE_REGISTRY 顺序执行
    4. 每步完成后记录 artifact hash
    """
    steps: dict[str, dict] = {}

    if not (doc := (await db.execute(
        select(KbDocument).where(KbDocument.id == document_id)
    )).scalar_one_or_none()):
        return {"error": f"Document {document_id} not found"}

    # ── 1. 检测 stale ──────────────────────────────
    stale_stages = set(await detect_stale_stages(db, document_id, file_id))

    # force = 手动标记 stale
    if force_raw:
        await mark_stale(db, document_id, "raw")
        stale_stages.add("raw")
    if force_fusion:
        await mark_stale(db, document_id, "fusion")
        stale_stages.add("fusion")

    # 记录当前源文件 hash
    await record_artifact_hash(db, document_id, "source_file", file_id)

    # ── 2. 按注册表顺序执行 ────────────────────────────
    completed_stages: set[str] = set()

    for stage_def in STAGE_REGISTRY:
        step_name = stage_def.name

        # 判断是否需要执行
        skip = False
        if stage_def.always_run:
            # always_run 始终执行，不受 stale 影响
            pass
        elif step_name not in stale_stages:
            # 非 stale 且已 done → 跳过
            status_field = f"{step_name}_status"
            current_status = getattr(doc, status_field, "pending")
            if current_status == "done":
                steps[step_name] = {"status": "skipped", "reason": "already done"}
                completed_stages.add(step_name)
                skip = True

        if skip:
            continue

        # 检查前置依赖是否完成
        for req in stage_def.requires:
            if req not in completed_stages:
                steps[step_name] = {"error": f"dependency '{req}' not completed", "status": "failed"}
                logger.error("Pipeline aborted at %s: dependency '%s' not completed for doc_id=%d",
                             step_name, req, document_id)
                return {"document_id": document_id, "status": "failed", "steps": steps}

        # 执行
        logger.info("Pipeline step %s: doc_id=%d", step_name, document_id)
        try:
            fn_kwargs: dict[str, Any] = {"db": db, "document_id": document_id, "owner_id": owner_id}
            if step_name == "raw":
                fn_kwargs.update(file_id=file_id, user_id=user_id)
            # profile/graph 只需要 db + document_id + owner_id
            # relations 只需要 db + document_id + owner_id
            steps[step_name] = await stage_def.fn(**fn_kwargs)
            await db.commit()

            # 检查执行结果是否有 error
            if "error" in steps[step_name]:
                logger.error("Pipeline step %s failed for doc_id=%d: %s",
                             step_name, document_id, steps[step_name].get("error"))
                return {"document_id": document_id, "status": "failed", "steps": steps}

            # 记录 hash
            await record_artifact_hash(db, document_id, step_name)

        except Exception as e:
            steps[step_name] = {"error": str(e)}
            logger.error("Pipeline step %s failed for doc_id=%d: %s", step_name, document_id, e)
            return {"document_id": document_id, "status": "failed", "steps": steps}

        completed_stages.add(step_name)

    # ── 3. 汇总 ────────────────────────────────────────
    has_errors = any("error" in s for s in steps.values())
    status = "done_with_errors" if has_errors else "done"
    return {"document_id": document_id, "status": status, "steps": steps}
