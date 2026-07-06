"""知识库 Pipeline 统一引擎（取代 _run_pipeline 的硬编码 5 步）。

设计：
- Stage 注册表：每个 stage 定义名称、依赖、是否始终执行、执行函数
- 统一调度：按注册表顺序迭代，检查 stale/force/状态决定是否跳过
- Hash 追踪：每步完成后记录 artifact hash，下次检测上游变化
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Awaitable, Callable

from app.database import AsyncSessionLocal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbDocument, KbPipelineRun, KbPipelineStageRun
from .analysis_artifact_service import (
    build_input_hash,
    build_output_hash,
    model_profile_from_result,
    model_used_from_result,
    record_analysis_artifact,
    resolve_stage_prompt_hash,
    stage_schema_version,
)
from .document_service import mark_document_source_unavailable
from .entity_service import process_document_entities_from_fusions
from .fusion_service import fuse_all_pages
from .model_routing import should_pause_after_result
from .profile_service import generate_document_profile
from .raw_collection_service import collect_raw_data
from .relation_service import compute_file_relations
from .source_file_state import get_source_file_availability
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
    always_run: bool           # True = 每次 pipeline 都执行（通常仅用于测试/手动强制）
    fn: StageFn                # 异步执行函数
    requires: list[str] = field(default_factory=list)  # 必须前置执行完的 stage


@dataclass(frozen=True)
class StageAssessment:
    """归一化 stage 结果语义。"""
    status: str
    complete_for_dependencies: bool
    reason: str = ""


FAILED_STATUSES = {"failed", "error"}
DEGRADED_STATUSES = {"degraded", "partial", "done_with_errors"}
STAGE_STATUS_FIELDS = {
    "raw": "raw_status",
    "fusion": "fusion_status",
    "profile": "profile_status",
    "graph": "graph_status",
    "relations": "relation_status",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    return str(value)


async def _start_pipeline_run(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    file_id: int,
    task_id: int | None = None,
) -> int | None:
    """Persist a best-effort pipeline run row for diagnostics."""
    _ = db
    diag_db = None
    try:
        async with AsyncSessionLocal() as session:
            diag_db = session
            run = KbPipelineRun(
                document_id=document_id,
                owner_id=owner_id,
                file_id=file_id,
                task_id=task_id,
                trigger="kb_pipeline",
                status="running",
                started_at=_now(),
            )
            session.add(run)
            await session.flush()
            run_id = int(run.id)
            await session.commit()
            return run_id
    except Exception as exc:
        if diag_db is not None:
            await diag_db.rollback()
        logger.warning("Pipeline run diagnostics start skipped doc_id=%d: %s", document_id, exc)
        return None


async def _finish_pipeline_run(
    db: AsyncSession,
    run_id: int | None,
    status: str,
    *,
    reason: str = "",
    diagnostics: dict | None = None,
) -> None:
    _ = db
    if run_id is None:
        return
    diag_db = None
    try:
        async with AsyncSessionLocal() as session:
            diag_db = session
            run = await session.get(KbPipelineRun, run_id)
            if run is None:
                return
            run.status = status
            run.reason = reason or None
            run.diagnostics_json = _json_safe(diagnostics or {})
            run.completed_at = _now()
            await session.commit()
    except Exception as exc:
        if diag_db is not None:
            await diag_db.rollback()
        logger.warning("Pipeline run diagnostics finish skipped run_id=%s: %s", run_id, exc)


async def _record_stage_run(
    db: AsyncSession,
    run_id: int | None,
    *,
    document_id: int,
    owner_id: int,
    stage: str,
    status: str,
    started_at: datetime,
    reason: str = "",
    metrics: dict | None = None,
    error_message: str = "",
    artifact_hash: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Persist one stage diagnostic row without making diagnostics flow-critical."""
    _ = db
    diag_db = None
    try:
        async with AsyncSessionLocal() as session:
            diag_db = session
            record = KbPipelineStageRun(
                run_id=run_id,
                document_id=document_id,
                owner_id=owner_id,
                stage=stage,
                status=status,
                reason=reason or None,
                artifact_hash=artifact_hash,
                metrics_json=_json_safe(metrics or {}),
                error_message=error_message or None,
                started_at=started_at,
                completed_at=_now(),
                duration_ms=duration_ms,
            )
            session.add(record)
            await session.commit()
    except Exception as exc:
        if diag_db is not None:
            await diag_db.rollback()
        logger.warning("Pipeline stage diagnostics skipped doc_id=%d stage=%s: %s", document_id, stage, exc)


async def _record_stage_artifact(
    db: AsyncSession,
    *,
    document_id: int,
    owner_id: int,
    file_id: int | None,
    stage: str,
    status: str,
    run_id: int | None = None,
    task_id: int | None = None,
    result: dict | None = None,
    reason: str = "",
    duration_ms: int | None = None,
    started_at: datetime | None = None,
    input_extra: dict | None = None,
    output_payload: Any | None = None,
    prompt_hash_value: str | None = None,
    output_hash_value: str | None = None,
) -> int | None:
    """Best-effort stable artifact ledger write for one pipeline stage."""
    result_payload = result or {}
    try:
        resolved_prompt_hash = prompt_hash_value
        if resolved_prompt_hash is None:
            resolved_prompt_hash = await resolve_stage_prompt_hash(db, stage)
    except Exception as exc:
        logger.warning("Prompt hash skipped doc_id=%d stage=%s: %s", document_id, stage, exc)
        resolved_prompt_hash = None

    input_hash = build_input_hash(
        stage=stage,
        document_id=document_id,
        file_id=file_id,
        extra=input_extra or {},
    )
    output_hash = output_hash_value or build_output_hash(
        stage=stage,
        status=status,
        payload=output_payload if output_payload is not None else result_payload,
    )
    diagnostics = {}
    if isinstance(result_payload.get("model_diagnostics"), dict):
        diagnostics["model_diagnostics"] = result_payload.get("model_diagnostics")
    elif isinstance(result_payload.get("model_diagnostics"), list):
        diagnostics["model_diagnostics"] = result_payload.get("model_diagnostics")
    if result_payload.get("timing"):
        diagnostics["timing"] = result_payload.get("timing")
    return await record_analysis_artifact(
        owner_id=owner_id,
        document_id=document_id,
        file_id=file_id,
        task_id=task_id,
        pipeline_run_id=run_id,
        stage=stage,
        status=status,
        input_hash=input_hash,
        output_hash=output_hash,
        prompt_hash_value=resolved_prompt_hash,
        model_profile=model_profile_from_result(result_payload),
        model_used=model_used_from_result(result_payload),
        schema_version=stage_schema_version(stage),
        reason=reason,
        diagnostics=_json_safe(diagnostics),
        metrics=_json_safe(result_payload),
        duration_ms=duration_ms,
        started_at=started_at,
        session_factory=AsyncSessionLocal,
    )


async def _abort_if_source_unavailable(
    db: AsyncSession,
    run_id: int | None,
    *,
    doc: KbDocument,
    document_id: int,
    owner_id: int,
    file_id: int,
    steps: dict[str, dict],
    stage: str,
    metrics: dict | None = None,
) -> dict | None:
    """Stop the pipeline if the source file disappeared during this run."""
    state = await get_source_file_availability(db, file_id)
    if state.available:
        return None

    mark_document_source_unavailable(doc, state.reason)
    await db.commit()
    step_payload = {
        "status": "skipped",
        "reason": state.reason,
        "classification": "source_unavailable",
    }
    if metrics:
        step_payload["metrics"] = metrics
    steps[stage] = step_payload
    await _record_stage_run(
        db,
        run_id,
        document_id=document_id,
        owner_id=owner_id,
        stage=stage,
        status="skipped",
        started_at=_now(),
        reason=state.reason,
        metrics=step_payload,
        duration_ms=0,
    )
    await _record_stage_artifact(
        db,
        document_id=document_id,
        owner_id=owner_id,
        file_id=file_id,
        run_id=run_id,
        stage=stage,
        status="skipped",
        result=step_payload,
        reason=state.reason,
        duration_ms=0,
        started_at=_now(),
        input_extra={"source_availability": state.reason},
    )
    await _finish_pipeline_run(
        db,
        run_id,
        "skipped",
        reason=state.reason,
        diagnostics={"steps": steps},
    )
    logger.info(
        "Pipeline skipped for document_id=%d file_id=%d during stage=%s: %s",
        document_id,
        file_id,
        stage,
        state.reason,
    )
    return {
        "document_id": document_id,
        "file_id": file_id,
        "status": "skipped",
        "reason": state.reason,
        "classification": "source_unavailable",
        "steps": steps,
    }


def assess_stage_result(stage_name: str, result: dict, required: bool = True) -> StageAssessment:
    """把各服务松散返回值归一为 done/degraded/failed/skipped 语义。

    required=True 表示该 stage 的产物会被后续 stage 当成依赖。required stage
    返回 skipped 或零有效内容时，pipeline 不再假装它已完成。
    """
    status_value = str(result.get("status") or "").lower()

    if result.get("error") not in (None, ""):
        return StageAssessment("failed", False, str(result.get("error")))
    if status_value in FAILED_STATUSES:
        return StageAssessment("failed", False, str(result.get("reason") or status_value))
    if result.get("model_degraded"):
        return StageAssessment("degraded", True, "model_fallback")
    if status_value == "skipped":
        reason = str(result.get("reason") or "skipped")
        return StageAssessment("degraded" if required else "skipped", not required, reason)

    if stage_name == "raw":
        total_rounds = int(result.get("total_rounds") or 0)
        valid_rounds = int(result.get("valid_rounds") or 0)
        if total_rounds > 0 and valid_rounds == 0:
            return StageAssessment("degraded", False, "raw_content_empty")
        primary_empty_pages = int(result.get("primary_empty_pages") or result.get("empty_pages") or 0)
        if primary_empty_pages > 0:
            return StageAssessment("degraded", True, "raw_content_partial")
        if status_value in DEGRADED_STATUSES:
            return StageAssessment("degraded", True, "raw_content_partial")

    if stage_name == "fusion":
        total_pages = int(result.get("total_pages") or 0)
        valid_pages = int(result.get("valid_pages") or 0)
        if total_pages > 0 and valid_pages == 0:
            return StageAssessment("degraded", False, "fusion_content_empty")
        if (
            int(result.get("empty_pages") or 0) > 0
            or result.get("index_error")
            or status_value in DEGRADED_STATUSES
        ):
            return StageAssessment("degraded", True, "fusion_content_partial")

    if stage_name == "profile":
        if not (result.get("subject") or result.get("doc_summary")) and status_value not in {"done", "ok", "success"}:
            return StageAssessment("degraded", False, "profile_content_empty")

    if stage_name == "graph" and result.get("errors"):
        return StageAssessment("degraded", False, "graph_content_empty")

    if status_value in DEGRADED_STATUSES:
        return StageAssessment("degraded", True, status_value)
    return StageAssessment("done", True, status_value or "done")


def _set_document_stage_status(doc: KbDocument, stage_name: str, status: str) -> None:
    field_name = STAGE_STATUS_FIELDS.get(stage_name)
    if not field_name:
        return
    if status == "skipped":
        return
    setattr(doc, field_name, status)


def _get_document_stage_status(doc: KbDocument, stage_name: str) -> str:
    field_name = STAGE_STATUS_FIELDS.get(stage_name)
    if not field_name:
        return "pending"
    return str(getattr(doc, field_name, "pending") or "pending")


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
        name="profile", deps=["fusion"], always_run=False,
        fn=generate_document_profile, requires=["fusion"],
    ),
    StageDef(
        name="graph", deps=["fusion"], always_run=False,
        fn=process_document_entities_from_fusions, requires=["fusion"],
    ),
    StageDef(
        name="relations", deps=["profile", "graph"], always_run=False,
        fn=compute_file_relations, requires=["profile", "graph"],
    ),
]


def _expand_stale_stages(stages: set[str]) -> set[str]:
    """Include all downstream stages affected by changed or forced upstream work."""
    expanded = set(stages)
    changed = True
    while changed:
        changed = False
        for stage_def in STAGE_REGISTRY:
            if stage_def.name in expanded:
                continue
            if any(dep in expanded for dep in stage_def.deps):
                expanded.add(stage_def.name)
                changed = True
    return expanded


async def run_pipeline(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    file_id: int,
    user_id: int,
    force_raw: bool = False,
    force_fusion: bool = False,
    task_id: int | None = None,
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

    run = await _start_pipeline_run(db, document_id, owner_id, file_id, task_id)

    aborted = await _abort_if_source_unavailable(
        db,
        run,
        doc=doc,
        document_id=document_id,
        owner_id=owner_id,
        file_id=file_id,
        steps=steps,
        stage="source_file",
    )
    if aborted:
        return aborted

    # ── 1. 检测 stale ──────────────────────────────
    stale_stages = set(await detect_stale_stages(db, document_id, file_id))

    # force = 手动标记 stale
    if force_raw:
        await mark_stale(db, document_id, "raw")
        stale_stages.add("raw")
    if force_fusion:
        await mark_stale(db, document_id, "fusion")
        stale_stages.add("fusion")
    stale_stages = _expand_stale_stages(stale_stages)

    # 记录当前源文件 hash
    source_started = _now()
    source_timer = perf_counter()
    source_hash = await record_artifact_hash(db, document_id, "source_file", file_id)
    await _record_stage_run(
        db,
        run,
        document_id=document_id,
        owner_id=owner_id,
        stage="source_file",
        status="done",
        started_at=source_started,
        reason="available",
        artifact_hash=source_hash,
        duration_ms=round((perf_counter() - source_timer) * 1000),
    )
    await _record_stage_artifact(
        db,
        document_id=document_id,
        owner_id=owner_id,
        file_id=file_id,
        task_id=task_id,
        run_id=run,
        stage="source_file",
        status="done",
        result={"status": "done", "reason": "available"},
        reason="available",
        duration_ms=round((perf_counter() - source_timer) * 1000),
        started_at=source_started,
        input_extra={"source_hash": source_hash},
        output_hash_value=source_hash,
    )

    # ── 2. 按注册表顺序执行 ────────────────────────────
    completed_stages: set[str] = set()
    failed_stages: set[str] = set()
    degraded_stages: set[str] = set()
    required_stage_names = {req for stage in STAGE_REGISTRY for req in stage.requires}

    for stage_def in STAGE_REGISTRY:
        step_name = stage_def.name

        aborted = await _abort_if_source_unavailable(
            db,
            run,
            doc=doc,
            document_id=document_id,
            owner_id=owner_id,
            file_id=file_id,
            steps=steps,
            stage=step_name,
        )
        if aborted:
            return aborted

        # 判断是否需要执行
        skip = False
        if stage_def.always_run:
            # always_run 始终执行，不受 stale 影响
            pass
        elif step_name not in stale_stages:
            # 非 stale 且已 done → 跳过
            current_status = _get_document_stage_status(doc, step_name)
            if current_status == "done":
                steps[step_name] = {"status": "skipped", "reason": "already done"}
                completed_stages.add(step_name)
                await _record_stage_run(
                    db,
                    run,
                    document_id=document_id,
                    owner_id=owner_id,
                    stage=step_name,
                    status="skipped",
                    started_at=_now(),
                    reason="already done",
                    metrics=steps[step_name],
                    duration_ms=0,
                )
                await _record_stage_artifact(
                    db,
                    document_id=document_id,
                    owner_id=owner_id,
                    file_id=file_id,
                    task_id=task_id,
                    run_id=run,
                    stage=step_name,
                    status="skipped",
                    result=steps[step_name],
                    reason="already done",
                    duration_ms=0,
                    started_at=_now(),
                    input_extra={"skip_reason": "already done"},
                )
                skip = True

        if skip:
            continue

        # 检查前置依赖是否完成
        for req in stage_def.requires:
            if req not in completed_stages:
                if req in failed_stages:
                    reason = f"dependency '{req}' failed"
                    steps[step_name] = {"error": reason, "status": "failed"}
                    await _record_stage_run(
                        db,
                        run,
                        document_id=document_id,
                        owner_id=owner_id,
                        stage=step_name,
                        status="failed",
                        started_at=_now(),
                        reason=reason,
                        metrics=steps[step_name],
                        error_message=reason,
                        duration_ms=0,
                    )
                    await _record_stage_artifact(
                        db,
                        document_id=document_id,
                        owner_id=owner_id,
                        file_id=file_id,
                        task_id=task_id,
                        run_id=run,
                        stage=step_name,
                        status="failed",
                        result=steps[step_name],
                        reason=reason,
                        duration_ms=0,
                        started_at=_now(),
                        input_extra={"dependency": req},
                    )
                    await _finish_pipeline_run(
                        db,
                        run,
                        "failed",
                        reason=reason,
                        diagnostics={"steps": steps},
                    )
                    await db.commit()
                    logger.error("Pipeline aborted at %s: dependency '%s' failed for doc_id=%d",
                                 step_name, req, document_id)
                    return {"document_id": document_id, "status": "failed", "steps": steps}
                steps[step_name] = {
                    "status": "skipped",
                    "reason": f"dependency '{req}' not available",
                    "classification": "degraded_dependency",
                }
                degraded_stages.add(step_name)
                _set_document_stage_status(doc, step_name, "degraded")
                await _record_stage_run(
                    db,
                    run,
                    document_id=document_id,
                    owner_id=owner_id,
                    stage=step_name,
                    status="degraded",
                    started_at=_now(),
                    reason=steps[step_name]["reason"],
                    metrics=steps[step_name],
                    duration_ms=0,
                )
                await _record_stage_artifact(
                    db,
                    document_id=document_id,
                    owner_id=owner_id,
                    file_id=file_id,
                    task_id=task_id,
                    run_id=run,
                    stage=step_name,
                    status="degraded",
                    result=steps[step_name],
                    reason=steps[step_name]["reason"],
                    duration_ms=0,
                    started_at=_now(),
                    input_extra={"dependency": req},
                )
                logger.warning("Pipeline skipped %s: dependency '%s' unavailable for doc_id=%d",
                               step_name, req, document_id)
                break
        if step_name in steps and steps[step_name].get("classification") == "degraded_dependency":
            continue

        # 执行
        logger.info("Pipeline step %s: doc_id=%d", step_name, document_id)
        stage_started = _now()
        stage_timer = perf_counter()
        try:
            _set_document_stage_status(doc, step_name, "running")
            await db.commit()
            fn_kwargs: dict[str, Any] = {"db": db, "document_id": document_id, "owner_id": owner_id}
            if step_name == "raw":
                fn_kwargs = {"db": db, "doc_id": document_id, "owner_id": owner_id, "file_id": file_id, "user_id": user_id}
            # profile/graph 只需要 db + document_id + owner_id
            # relations 只需要 db + document_id + owner_id
            steps[step_name] = await stage_def.fn(**fn_kwargs)
            await db.commit()

            aborted = await _abort_if_source_unavailable(
                db,
                run,
                doc=doc,
                document_id=document_id,
                owner_id=owner_id,
                file_id=file_id,
                steps=steps,
                stage=step_name,
                metrics=steps[step_name],
            )
            if aborted:
                return aborted

            assessment = assess_stage_result(
                step_name,
                steps[step_name],
                required=step_name in required_stage_names,
            )
            steps[step_name]["stage_status"] = assessment.status
            if assessment.reason and "stage_reason" not in steps[step_name]:
                steps[step_name]["stage_reason"] = assessment.reason
            pause_after_stage = False

            if assessment.status == "failed":
                failed_stages.add(step_name)
                _set_document_stage_status(doc, step_name, "failed")
                await _record_stage_run(
                    db,
                    run,
                    document_id=document_id,
                    owner_id=owner_id,
                    stage=step_name,
                    status="failed",
                    started_at=stage_started,
                    reason=assessment.reason,
                    metrics=steps[step_name],
                    error_message=assessment.reason,
                    duration_ms=round((perf_counter() - stage_timer) * 1000),
                )
                await _record_stage_artifact(
                    db,
                    document_id=document_id,
                    owner_id=owner_id,
                    file_id=file_id,
                    task_id=task_id,
                    run_id=run,
                    stage=step_name,
                    status="failed",
                    result=steps[step_name],
                    reason=assessment.reason,
                    duration_ms=round((perf_counter() - stage_timer) * 1000),
                    started_at=stage_started,
                )
                await _finish_pipeline_run(db, run, "failed", reason=assessment.reason, diagnostics={"steps": steps})
                await db.commit()
                logger.error("Pipeline step %s failed for doc_id=%d: %s",
                             step_name, document_id, assessment.reason)
                return {"document_id": document_id, "status": "failed", "steps": steps}
            if assessment.status == "degraded":
                degraded_stages.add(step_name)
                _set_document_stage_status(doc, step_name, "degraded")
                logger.warning("Pipeline step %s degraded for doc_id=%d: %s",
                               step_name, document_id, assessment.reason)
                pause_after_stage = should_pause_after_result(steps[step_name])
            elif assessment.status == "done":
                _set_document_stage_status(doc, step_name, "done")

            # 记录 hash

            artifact_hash = None
            if assessment.complete_for_dependencies:
                artifact_hash = await record_artifact_hash(db, document_id, step_name)
                completed_stages.add(step_name)
            await _record_stage_run(
                db,
                run,
                document_id=document_id,
                owner_id=owner_id,
                stage=step_name,
                status=assessment.status,
                started_at=stage_started,
                reason=assessment.reason,
                metrics=steps[step_name],
                artifact_hash=artifact_hash,
                duration_ms=round((perf_counter() - stage_timer) * 1000),
            )
            await _record_stage_artifact(
                db,
                document_id=document_id,
                owner_id=owner_id,
                file_id=file_id,
                task_id=task_id,
                run_id=run,
                stage=step_name,
                status=assessment.status,
                result=steps[step_name],
                reason=assessment.reason,
                duration_ms=round((perf_counter() - stage_timer) * 1000),
                started_at=stage_started,
            )
            if pause_after_stage:
                pause_reason = "model_fallback_pause"
                steps["_pause"] = {
                    "status": "paused",
                    "reason": pause_reason,
                    "after_stage": step_name,
                    "model_diagnostics": steps[step_name].get("model_diagnostics"),
                }
                await _record_stage_run(
                    db,
                    run,
                    document_id=document_id,
                    owner_id=owner_id,
                    stage="pause",
                    status="paused",
                    started_at=_now(),
                    reason=pause_reason,
                    metrics=steps["_pause"],
                    duration_ms=0,
                )
                await _record_stage_artifact(
                    db,
                    document_id=document_id,
                    owner_id=owner_id,
                    file_id=file_id,
                    task_id=task_id,
                    run_id=run,
                    stage="pause",
                    status="paused",
                    result=steps["_pause"],
                    reason=pause_reason,
                    duration_ms=0,
                    started_at=_now(),
                )
                await _finish_pipeline_run(db, run, "paused", reason=pause_reason, diagnostics={"steps": steps})
                await db.commit()
                logger.warning(
                    "Pipeline paused after model fallback at %s for doc_id=%d",
                    step_name,
                    document_id,
                )
                return {"document_id": document_id, "status": "paused", "reason": pause_reason, "steps": steps}

        except Exception as e:
            steps[step_name] = {"error": str(e)}
            _set_document_stage_status(doc, step_name, "failed")
            await _record_stage_run(
                db,
                run,
                document_id=document_id,
                owner_id=owner_id,
                stage=step_name,
                status="failed",
                started_at=stage_started,
                reason=str(e),
                metrics=steps[step_name],
                error_message=str(e),
                duration_ms=round((perf_counter() - stage_timer) * 1000),
            )
            await _record_stage_artifact(
                db,
                document_id=document_id,
                owner_id=owner_id,
                file_id=file_id,
                task_id=task_id,
                run_id=run,
                stage=step_name,
                status="failed",
                result=steps[step_name],
                reason=str(e),
                duration_ms=round((perf_counter() - stage_timer) * 1000),
                started_at=stage_started,
            )
            await _finish_pipeline_run(db, run, "failed", reason=str(e), diagnostics={"steps": steps})
            await db.commit()
            logger.error("Pipeline step %s failed for doc_id=%d: %s", step_name, document_id, e)
            return {"document_id": document_id, "status": "failed", "steps": steps}

    # ── 3. 汇总 ────────────────────────────────────────
    status = "degraded" if degraded_stages else "done"
    await _finish_pipeline_run(
        db,
        run,
        status,
        reason=";".join(sorted(degraded_stages)) if degraded_stages else "",
        diagnostics={"steps": steps},
    )
    await db.commit()
    return {"document_id": document_id, "status": status, "steps": steps}
