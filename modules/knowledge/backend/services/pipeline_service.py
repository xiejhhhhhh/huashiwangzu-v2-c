"""Knowledge analysis DAG queue.

The worker queue has one knowledge task type: ``kb_pipeline_stage``. Each task
executes one durable stage and then enqueues newly-unblocked downstream stages.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from app.database import AsyncSessionLocal
from app.models.system import SystemTaskQueue
from app.services.task_worker import register_task_handler
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    KbDocument,
    KbPipelineRun,
    KbPipelineStageRun,
    KbRawData,
    KbTermOccurrence,
)
from .analysis_artifact_service import (
    build_input_hash,
    build_output_hash,
    model_profile_from_result,
    model_used_from_result,
    record_analysis_artifact,
    resolve_stage_prompt_hash,
    stage_schema_version,
)
from .cognitive_v3_service import derive_document_cognitive_index
from .document_service import (
    NON_CONTENT_FILE_REASONS,
    SOURCE_UNAVAILABLE_REASONS,
    document_deep_pipeline_complete,
    document_parse_allows_search,
    document_vector_stage_terminal,
    mark_document_non_content_skipped,
    mark_document_source_unavailable,
    parse_and_index_document,
)
from .entity_service import process_document_entities_from_fusions
from .fusion_service import fuse_all_pages
from .model_routing import (
    is_model_stage,
    pause_model_stage_queue,
    record_model_rate_limit,
    resolve_knowledge_concurrency,
    resolve_knowledge_pipeline_priority,
    should_pause_after_result,
)
from .page_asset_service import materialize_page_assets_stage, page_assets_complete
from .profile_service import generate_document_profile
from .raw_collection_service import collect_raw_stage
from .relation_service import compute_file_relations
from .source_file_state import classify_non_content_file, get_source_file_availability, raise_if_source_unavailable
from .stage_result_cache_service import delete_stage_result_cache, write_stage_result_cache

logger = logging.getLogger("v2.knowledge").getChild("pipeline")

PIPELINE_TASK_TYPE = "kb_pipeline_stage"
ROOT_STAGE = "source_validate"
PIPELINE_STAGES = {
    "source_validate",
    "parse_index",
    "raw_text",
    "page_render",
    "raw_ocr",
    "raw_vision",
    "fusion",
    "profile",
    "cognitive_index",
    "graph",
    "relations",
}
VISUAL_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "svg"}
RAW_STAGE_TO_ROUND = {
    "raw_text": 1,
    "raw_ocr": 2,
    "raw_vision": 3,
}
STAGE_LANE_KEYS = {
    ROOT_STAGE: "local_preprocess",
    "parse_index": "local_preprocess",
    "raw_text": "local_preprocess",
    "page_render": "local_preprocess",
    "raw_ocr": "model_analysis",
    "raw_vision": "model_analysis",
    "fusion": "model_analysis",
    "profile": "model_analysis",
    "cognitive_index": "derived_index",
    "graph": "model_analysis",
    "relations": "relation_build",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_params(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_safe(value: Any) -> Any:
    """Convert stage outputs to JSON-safe values before persisting ledgers."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted((_json_safe(item) for item in value), key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
    return value


def _task_matches(task: SystemTaskQueue, document_id: int, stage: str) -> bool:
    return task.document_id == int(document_id) and str(task.stage_key or "") == stage


async def _find_active_stage_task(db: AsyncSession, document_id: int, stage: str) -> SystemTaskQueue | None:
    document_id_value = int(document_id)
    result = await db.execute(
        select(SystemTaskQueue)
        .where(
            SystemTaskQueue.module == "knowledge",
            SystemTaskQueue.task_type == PIPELINE_TASK_TYPE,
            SystemTaskQueue.status.in_(("pending", "running")),
            SystemTaskQueue.document_id == document_id_value,
            SystemTaskQueue.stage_key == stage,
        )
        .order_by(SystemTaskQueue.id.desc())
    )
    for task in result.scalars().all():
        if _task_matches(task, document_id, stage):
            return task
    return None


async def enqueue_pipeline_stage_task(
    db: AsyncSession,
    doc: KbDocument,
    user_id: int,
    stage: str = ROOT_STAGE,
    *,
    priority: int = 5,
    pipeline_run_id: int | None = None,
    force_raw: bool = False,
    force_fusion: bool = False,
) -> dict:
    """Enqueue one DAG stage, deduping active work for the same document/stage."""
    if stage not in PIPELINE_STAGES:
        raise ValueError(f"Unknown knowledge pipeline stage: {stage}")
    resolved_priority = resolve_knowledge_pipeline_priority(stage, priority)

    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :document_id)"),
        {"namespace": 1262633040, "document_id": int(doc.id) % 2147483647},
    )
    existing = await _find_active_stage_task(db, int(doc.id), stage)
    if existing:
        return {
            "task_id": int(existing.id),
            "enqueued": False,
            "reason": "stage_already_in_flight",
            "stage": stage,
            "next_task": PIPELINE_TASK_TYPE,
        }

    payload = {
        "document_id": int(doc.id),
        "user_id": int(user_id),
        "stage": stage,
        "pipeline_run_id": pipeline_run_id,
        "force_raw": bool(force_raw),
        "force_fusion": bool(force_fusion),
    }
    task = SystemTaskQueue(
        task_type=PIPELINE_TASK_TYPE,
        module="knowledge",
        parameters=json.dumps(payload, ensure_ascii=False),
        priority=resolved_priority,
        status="pending",
        creator_id=user_id,
        document_id=int(doc.id),
        stage_key=stage,
        lane_key=STAGE_LANE_KEYS.get(stage, "knowledge"),
        ready_status="ready",
        dependency_key=f"knowledge:{int(doc.id)}:{stage}",
    )
    db.add(task)
    await db.flush()
    payload["task_id"] = int(task.id)
    task.parameters = json.dumps(payload, ensure_ascii=False)
    return {
        "task_id": int(task.id),
        "enqueued": True,
        "reason": "stage_created",
        "stage": stage,
        "next_task": PIPELINE_TASK_TYPE,
    }


async def _ensure_pipeline_run(
    db: AsyncSession,
    *,
    doc: KbDocument,
    task_id: int | None,
    pipeline_run_id: int | None,
) -> int | None:
    if pipeline_run_id:
        existing = await db.get(KbPipelineRun, int(pipeline_run_id))
        if existing is not None:
            return int(existing.id)

    run = KbPipelineRun(
        document_id=int(doc.id),
        owner_id=int(doc.owner_id),
        file_id=int(doc.file_id),
        task_id=task_id,
        trigger=PIPELINE_TASK_TYPE,
        status="running",
        started_at=_now(),
    )
    db.add(run)
    await db.flush()
    return int(run.id)


async def _finish_pipeline_run(
    db: AsyncSession,
    pipeline_run_id: int | None,
    status: str,
    *,
    reason: str = "",
    diagnostics: dict | None = None,
) -> None:
    if pipeline_run_id is None:
        return
    run = await db.get(KbPipelineRun, int(pipeline_run_id))
    if run is None:
        return
    run.status = status
    run.reason = reason or None
    run.diagnostics_json = _json_safe(diagnostics or {})
    run.completed_at = _now()


async def _record_stage_run(
    db: AsyncSession,
    *,
    doc: KbDocument,
    pipeline_run_id: int | None,
    stage: str,
    status: str,
    started_at: datetime,
    result: dict,
    reason: str = "",
    error_message: str = "",
    artifact_hash: str | None = None,
    duration_ms: int | None = None,
) -> None:
    db.add(
        KbPipelineStageRun(
            run_id=pipeline_run_id,
            document_id=int(doc.id),
            owner_id=int(doc.owner_id),
            stage=stage,
            status=status,
            reason=reason or None,
            artifact_hash=artifact_hash,
            metrics_json=_json_safe(result),
            error_message=error_message or None,
            started_at=started_at,
            completed_at=_now(),
            duration_ms=duration_ms,
        )
    )


async def _record_stage_artifact(
    db: AsyncSession,
    *,
    doc: KbDocument,
    pipeline_run_id: int | None,
    task_id: int | None,
    stage: str,
    status: str,
    started_at: datetime,
    result: dict,
    reason: str = "",
    duration_ms: int | None = None,
) -> str:
    """Persist a best-effort artifact ledger row for the unified DAG stage."""
    safe_result = _json_safe(result)
    diagnostics: dict[str, Any] = {}
    if isinstance(safe_result.get("model_diagnostics"), dict | list):
        diagnostics["model_diagnostics"] = safe_result.get("model_diagnostics")
    if safe_result.get("timing"):
        diagnostics["timing"] = safe_result.get("timing")
    if safe_result.get("pause"):
        diagnostics["pause"] = safe_result.get("pause")

    input_hash = build_input_hash(
        stage=stage,
        document_id=int(doc.id),
        file_id=int(doc.file_id),
        extra={
            "task_id": task_id,
            "pipeline_run_id": pipeline_run_id,
            "document_status": {
                "parse": getattr(doc, "parse_status", None),
                "vector": getattr(doc, "vector_status", None),
                "raw": getattr(doc, "raw_status", None),
                "fusion": getattr(doc, "fusion_status", None),
                "profile": getattr(doc, "profile_status", None),
                "graph": getattr(doc, "graph_status", None),
                "relations": getattr(doc, "relation_status", None),
            },
        },
    )
    output_hash = build_output_hash(stage=stage, status=status, payload=safe_result)
    try:
        prompt_hash_value = await resolve_stage_prompt_hash(db, stage)
    except Exception as exc:
        logger.warning("Prompt hash skipped doc_id=%d stage=%s: %s", int(doc.id), stage, exc)
        prompt_hash_value = None

    await record_analysis_artifact(
        owner_id=int(doc.owner_id),
        document_id=int(doc.id),
        file_id=int(doc.file_id),
        task_id=task_id,
        pipeline_run_id=pipeline_run_id,
        stage=stage,
        status=status,
        input_hash=input_hash,
        output_hash=output_hash,
        prompt_hash_value=prompt_hash_value,
        model_profile=model_profile_from_result(safe_result),
        model_used=model_used_from_result(safe_result),
        schema_version=stage_schema_version(stage),
        reason=reason,
        diagnostics=diagnostics,
        metrics=safe_result,
        duration_ms=duration_ms,
        started_at=started_at,
    )
    return output_hash


def _is_visual_document(doc: KbDocument) -> bool:
    return (doc.extension or "").lower() in VISUAL_EXTENSIONS


def _raw_required_rounds(doc: KbDocument) -> list[int]:
    return [1, 2, 3] if _is_visual_document(doc) else [1]


async def _raw_round_complete(db: AsyncSession, doc: KbDocument, round_num: int) -> bool:
    total_pages = int(doc.total_pages or 1)
    result = await db.execute(
        select(KbRawData.page, KbRawData.status).where(
            KbRawData.document_id == int(doc.id),
            KbRawData.round == int(round_num),
        )
    )
    completed = {
        int(page)
        for page, status in result.all()
        if str(status or "") in {"done", "degraded"}
    }
    return all(page in completed for page in range(1, total_pages + 1))


async def _raw_complete(db: AsyncSession, doc: KbDocument) -> bool:
    for round_num in _raw_required_rounds(doc):
        if not await _raw_round_complete(db, doc, round_num):
            return False
    return True


def _parse_index_ready(doc: KbDocument) -> bool:
    return document_parse_allows_search(doc)


async def _ready_for_fusion(db: AsyncSession, doc: KbDocument) -> bool:
    return _parse_index_ready(doc) and await _raw_complete(db, doc)


def _ready_for_relations(doc: KbDocument) -> bool:
    return (
        str(getattr(doc, "profile_status", "pending") or "pending") == "done"
        and str(getattr(doc, "graph_status", "pending") or "pending") == "done"
    )


def _ready_for_cognitive_index(doc: KbDocument) -> bool:
    return (
        str(getattr(doc, "fusion_status", "pending") or "pending") == "done"
        and str(getattr(doc, "profile_status", "pending") or "pending") == "done"
    )


async def _cognitive_index_complete(db: AsyncSession, doc: KbDocument) -> bool:
    existing = await db.scalar(
        select(KbTermOccurrence.id)
        .where(
            KbTermOccurrence.owner_id == int(doc.owner_id),
            KbTermOccurrence.document_id == int(doc.id),
        )
        .limit(1)
    )
    return existing is not None


def _stage_needs_work(status: str | None) -> bool:
    return str(status or "pending").lower() in {"", "pending", "running", "collecting", "parsing", "fusing"}


async def _enqueue_successors(
    db: AsyncSession,
    *,
    doc: KbDocument,
    user_id: int,
    completed_stage: str,
    pipeline_run_id: int | None,
    force_raw: bool = False,
    force_fusion: bool = False,
) -> list[dict]:
    enqueued: list[dict] = []
    if hasattr(db, "scalar"):
        fresh_doc = await db.scalar(select(KbDocument).where(KbDocument.id == int(doc.id)))
        if fresh_doc is None:
            return enqueued
        doc = fresh_doc

    if completed_stage == ROOT_STAGE:
        visual_assets_missing = (
            _is_visual_document(doc)
            and not await page_assets_complete(db, document_id=int(doc.id), total_pages=int(doc.total_pages or 1))
        )
        needs_deep_work = force_raw or not document_deep_pipeline_complete(doc, source_available=True)
        if needs_deep_work:
            enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "parse_index", priority=8, pipeline_run_id=pipeline_run_id))
            enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "raw_text", priority=8, pipeline_run_id=pipeline_run_id))
        if _is_visual_document(doc) and (needs_deep_work or visual_assets_missing):
            enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "page_render", priority=8, pipeline_run_id=pipeline_run_id))
        return enqueued

    if completed_stage == "page_render":
        enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "raw_ocr", priority=8, pipeline_run_id=pipeline_run_id))
        enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "raw_vision", priority=8, pipeline_run_id=pipeline_run_id))
        return enqueued

    if completed_stage in {"parse_index", "raw_text", "raw_ocr", "raw_vision"}:
        if force_raw or str(getattr(doc, "raw_status", "pending") or "pending") != "done":
            raw_ready = await _raw_complete(db, doc)
        else:
            raw_ready = True
        if raw_ready and await _ready_for_fusion(db, doc):
            enqueued.append(
                await enqueue_pipeline_stage_task(
                    db,
                    doc,
                    user_id,
                    "fusion",
                    priority=7,
                    pipeline_run_id=pipeline_run_id,
                    force_fusion=force_fusion,
                )
            )
        return enqueued

    if completed_stage == "fusion":
        enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "profile", priority=6, pipeline_run_id=pipeline_run_id))
        enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "graph", priority=6, pipeline_run_id=pipeline_run_id))
        return enqueued

    if completed_stage in {"profile", "graph"}:
        if completed_stage == "profile" and _ready_for_cognitive_index(doc) and not await _cognitive_index_complete(db, doc):
            enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "cognitive_index", priority=5, pipeline_run_id=pipeline_run_id))
        if _ready_for_relations(doc):
            enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "relations", priority=5, pipeline_run_id=pipeline_run_id))
        elif _stage_needs_work(getattr(doc, "profile_status", "pending")):
            enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "profile", priority=6, pipeline_run_id=pipeline_run_id))
        elif _stage_needs_work(getattr(doc, "graph_status", "pending")):
            enqueued.append(await enqueue_pipeline_stage_task(db, doc, user_id, "graph", priority=6, pipeline_run_id=pipeline_run_id))
        return enqueued

    if completed_stage == "cognitive_index":
        return enqueued

    return enqueued


async def _run_stage(
    db: AsyncSession,
    *,
    doc: KbDocument,
    user_id: int,
    stage: str,
    task_id: int | None = None,
    force_raw: bool = False,
    force_fusion: bool = False,
) -> dict:
    if stage == ROOT_STAGE:
        source_state = await get_source_file_availability(db, int(doc.file_id))
        if not source_state.available:
            mark_document_source_unavailable(doc, source_state.reason)
            await db.commit()
            return {"document_id": int(doc.id), "status": "skipped", "reason": source_state.reason}
        if (doc.parse_error or "") in SOURCE_UNAVAILABLE_REASONS:
            doc.parse_error = None
        non_content_reason = classify_non_content_file(doc, source_state.physical_path)
        if non_content_reason:
            mark_document_non_content_skipped(doc, non_content_reason)
            await db.commit()
            return {
                "document_id": int(doc.id),
                "file_id": int(doc.file_id),
                "status": "skipped",
                "reason": non_content_reason,
            }
        return {"document_id": int(doc.id), "status": "done", "reason": "source_available"}

    if stage == "parse_index":
        if _parse_index_ready(doc) and document_vector_stage_terminal(doc) and not force_raw:
            return {"document_id": int(doc.id), "status": "skipped", "reason": "already done"}
        result = await parse_and_index_document(
            db,
            document_id=int(doc.id),
            owner_id=int(doc.owner_id),
            caller=f"user:{user_id}",
            extract_graph=False,
            current_task_id=task_id,
        )
        await db.refresh(doc)
        return {"status": "done" if document_parse_allows_search(doc) else "degraded", **result}

    if stage in RAW_STAGE_TO_ROUND:
        result = await collect_raw_stage(db, int(doc.id), int(doc.owner_id), int(doc.file_id), int(user_id), stage)
        if result.get("raw_complete") and str(getattr(doc, "raw_status", "pending") or "pending") == "collecting":
            doc.raw_status = "done"
        return result

    if stage == "page_render":
        return await materialize_page_assets_stage(db, int(doc.id), int(doc.owner_id), int(doc.file_id), int(user_id))

    if stage == "fusion":
        if str(getattr(doc, "fusion_status", "pending") or "pending") == "done" and not force_fusion:
            return {"document_id": int(doc.id), "status": "skipped", "reason": "already done"}
        if not await _ready_for_fusion(db, doc):
            return {"document_id": int(doc.id), "status": "blocked", "reason": "upstream_not_ready"}
        return await fuse_all_pages(db, int(doc.id), int(doc.owner_id))

    if stage == "profile":
        if str(getattr(doc, "profile_status", "pending") or "pending") == "done":
            return {"document_id": int(doc.id), "status": "skipped", "reason": "already done"}
        result = await generate_document_profile(db, int(doc.id), int(doc.owner_id))
        await db.refresh(doc)
        if result.get("status") == "skipped":
            doc.profile_status = "degraded"
        return result

    if stage == "graph":
        if str(getattr(doc, "graph_status", "pending") or "pending") == "done":
            return {"document_id": int(doc.id), "status": "skipped", "reason": "already done"}
        result = await process_document_entities_from_fusions(db, int(doc.id), int(doc.owner_id))
        await db.refresh(doc)
        doc.graph_status = "degraded" if result.get("status") == "degraded" else "done"
        return {"status": doc.graph_status, **result}

    if stage == "cognitive_index":
        if await _cognitive_index_complete(db, doc):
            return {"document_id": int(doc.id), "status": "skipped", "reason": "already done"}
        if not _ready_for_cognitive_index(doc):
            return {"document_id": int(doc.id), "status": "blocked", "reason": "upstream_not_ready"}
        limit = resolve_knowledge_concurrency(
            "cognitive_terms_per_document",
            200,
            minimum=20,
            maximum=1000,
        )
        result = await derive_document_cognitive_index(
            db,
            owner_id=int(doc.owner_id),
            document_id=int(doc.id),
            limit=limit,
        )
        return {"status": "done", "document_id": int(doc.id), "limit": limit, **result}

    if stage == "relations":
        if str(getattr(doc, "relation_status", "pending") or "pending") == "done":
            return {"document_id": int(doc.id), "status": "skipped", "reason": "already done"}
        result = await compute_file_relations(db, int(doc.id), int(doc.owner_id))
        await db.refresh(doc)
        doc.relation_status = "done"
        return {"status": "done", **result}

    return {"document_id": int(doc.id), "status": "failed", "error": f"unknown stage {stage}"}


def _stage_status_from_result(result: dict) -> tuple[str, str]:
    if result.get("error"):
        return "failed", str(result.get("error"))
    status = str(result.get("status") or "done").lower()
    if status in {"failed", "error"}:
        return "failed", str(result.get("reason") or status)
    if status in {"skipped", "blocked"}:
        return status, str(result.get("reason") or status)
    if status in {"degraded", "partial", "done_with_errors"} or result.get("model_degraded"):
        return "degraded", str(result.get("reason") or ("model_fallback" if result.get("model_degraded") else status))
    return "done", str(result.get("reason") or status or "done")


def _is_terminal_skip(reason: str) -> bool:
    return (
        reason in SOURCE_UNAVAILABLE_REASONS
        or reason in NON_CONTENT_FILE_REASONS
        or reason in {"doc_missing", "doc_deleted"}
    )


async def _release_stage_transaction(db: AsyncSession, *, document_id: int, stage: str) -> None:
    """Best-effort release before long stage work; final writes still enforce errors."""
    try:
        await db.commit()
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            logger.warning(
                "Knowledge pipeline pre-stage rollback failed doc_id=%d stage=%s",
                document_id,
                stage,
                exc_info=True,
            )
        logger.warning(
            "Knowledge pipeline pre-stage transaction release failed doc_id=%d stage=%s: %s",
            document_id,
            stage,
            exc,
        )


async def _pipeline_stage_handler(params: dict) -> dict:
    document_id = int(params.get("document_id", 0) or 0)
    user_id = int(params.get("user_id", 0) or 0) or 1
    stage = str(params.get("stage") or ROOT_STAGE)
    task_id = int(params.get("task_id", 0) or 0) or None
    pipeline_run_id = int(params.get("pipeline_run_id", 0) or 0) or None
    force_raw = bool(params.get("force_raw", False))
    force_fusion = bool(params.get("force_fusion", False))
    if document_id <= 0:
        return {"status": "failed", "error": "document_id required"}
    if stage not in PIPELINE_STAGES:
        return {"document_id": document_id, "status": "failed", "error": f"unknown stage {stage}"}

    async with AsyncSessionLocal() as db:
        doc = await db.scalar(select(KbDocument).where(KbDocument.id == document_id))
        if doc is None:
            return {"document_id": document_id, "status": "skipped", "reason": "doc_missing", "classification": "obsolete"}
        if doc.deleted:
            return {"document_id": document_id, "file_id": doc.file_id, "status": "skipped", "reason": "doc_deleted", "classification": "obsolete"}

        started_at = _now()
        timer = perf_counter()
        pipeline_run_id = await _ensure_pipeline_run(db, doc=doc, task_id=task_id, pipeline_run_id=pipeline_run_id)
        await _release_stage_transaction(db, document_id=document_id, stage=stage)
        file_id = int(doc.file_id)
        try:
            await raise_if_source_unavailable(db, file_id)
            await _release_stage_transaction(db, document_id=document_id, stage=stage)
            non_content_reason = classify_non_content_file(doc)
            if non_content_reason:
                mark_document_non_content_skipped(doc, non_content_reason)
                await db.commit()
                result = {
                    "document_id": document_id,
                    "file_id": file_id,
                    "status": "skipped",
                    "reason": non_content_reason,
                }
            else:
                result = await _run_stage(
                    db,
                    doc=doc,
                    user_id=user_id,
                    stage=stage,
                    task_id=task_id,
                    force_raw=force_raw,
                    force_fusion=force_fusion,
                )
        except Exception as exc:
            try:
                await db.rollback()
            except Exception as rollback_exc:
                logger.warning(
                    "Knowledge pipeline rollback failed doc_id=%d stage=%s: %s",
                    document_id,
                    stage,
                    rollback_exc,
                )
            fresh_doc = await db.scalar(select(KbDocument).where(KbDocument.id == document_id))
            if fresh_doc is not None:
                doc = fresh_doc
                file_id = int(doc.file_id)
            source_state = await get_source_file_availability(db, file_id)
            if not source_state.available:
                mark_document_source_unavailable(doc, source_state.reason)
                result = {"document_id": document_id, "status": "skipped", "reason": source_state.reason}
            else:
                result = {"document_id": document_id, "status": "failed", "error": str(exc)}
                if is_model_stage(stage):
                    rate_limit_pause = record_model_rate_limit(stage, error_message=exc)
                    if rate_limit_pause.get("paused"):
                        result["pause"] = {
                            "status": "paused",
                            "reason": "model_rate_limit_threshold",
                            "after_stage": stage,
                            **rate_limit_pause,
                        }
                    else:
                        result["rate_limit"] = rate_limit_pause
                    should_fallback_pause = rate_limit_pause.get("reason") != "below_threshold"
                    pause_result = pause_model_stage_queue(
                        stage,
                        reason="model_fallback_exhausted",
                        error_message=str(exc),
                    ) if should_fallback_pause else {"paused": False, "reason": "rate_limit_below_threshold"}
                    if pause_result.get("paused") and "pause" not in result:
                        result["pause"] = {
                            "status": "paused",
                            "reason": "model_fallback_exhausted",
                            "after_stage": stage,
                            **pause_result,
                        }
                logger.error("Knowledge pipeline stage failed doc_id=%d stage=%s: %s", document_id, stage, exc)

        status, reason = _stage_status_from_result(result)
        duration_ms = round((perf_counter() - timer) * 1000)
        stage_result_cache_path = write_stage_result_cache(
            document_id=document_id,
            file_id=int(doc.file_id),
            owner_id=int(doc.owner_id),
            stage=stage,
            status=status,
            result=_json_safe(result),
            task_id=task_id,
            pipeline_run_id=pipeline_run_id,
            reason=reason,
            started_at=started_at,
            duration_ms=duration_ms,
        )
        await db.flush()
        successors: list[dict] = []
        if status in {"done", "degraded", "skipped"}:
            if should_pause_after_result(result):
                await _finish_pipeline_run(
                    db,
                    pipeline_run_id,
                    "paused",
                    reason="model_fallback_pause",
                    diagnostics={"stage": stage, "result": result},
                )
                result["pause"] = {"status": "paused", "reason": "model_fallback_pause", "after_stage": stage}
                await _record_stage_run(
                    db,
                    doc=doc,
                    pipeline_run_id=pipeline_run_id,
                    stage="pause",
                    status="paused",
                    started_at=_now(),
                    result=result["pause"],
                    reason="model_fallback_pause",
                    duration_ms=0,
                )
                await _record_stage_artifact(
                    db,
                    doc=doc,
                    pipeline_run_id=pipeline_run_id,
                    task_id=task_id,
                    stage="pause",
                    status="paused",
                    started_at=_now(),
                    result=result["pause"],
                    reason="model_fallback_pause",
                    duration_ms=0,
                )
            elif status == "skipped" and _is_terminal_skip(reason):
                await _finish_pipeline_run(
                    db,
                    pipeline_run_id,
                    "skipped",
                    reason=reason,
                    diagnostics={"stage": stage, "result": result},
                )
            else:
                successors = await _enqueue_successors(
                    db,
                    doc=doc,
                    user_id=user_id,
                    completed_stage=stage,
                    pipeline_run_id=pipeline_run_id,
                    force_raw=force_raw,
                    force_fusion=force_fusion,
                )
                await _release_stage_transaction(db, document_id=document_id, stage=stage)
                doc = await db.scalar(select(KbDocument).where(KbDocument.id == document_id)) or doc
                if stage == "relations":
                    await _finish_pipeline_run(db, pipeline_run_id, "done", diagnostics={"last_stage": stage})
                elif not successors:
                    await db.refresh(doc)
                    if document_deep_pipeline_complete(doc, source_available=True):
                        await _finish_pipeline_run(db, pipeline_run_id, "done", diagnostics={"last_stage": stage})
                    elif status == "degraded" and stage in {"profile", "graph", "fusion"}:
                        await _finish_pipeline_run(
                            db,
                            pipeline_run_id,
                            "degraded",
                            reason=reason,
                            diagnostics={"last_stage": stage, "result": result},
                        )
        elif status == "failed":
            await _finish_pipeline_run(db, pipeline_run_id, "failed", reason=reason, diagnostics={"stage": stage, "result": result})

        artifact_hash = await _record_stage_artifact(
            db,
            doc=doc,
            pipeline_run_id=pipeline_run_id,
            task_id=task_id,
            stage=stage,
            status=status,
            started_at=started_at,
            result=result,
            reason=reason,
            duration_ms=duration_ms,
        )
        await _record_stage_run(
            db,
            doc=doc,
            pipeline_run_id=pipeline_run_id,
            stage=stage,
            status=status,
            started_at=started_at,
            result=result,
            reason=reason,
            error_message=reason if status == "failed" else "",
            artifact_hash=artifact_hash,
            duration_ms=duration_ms,
        )
        await db.commit()
        delete_stage_result_cache(stage_result_cache_path)
        return {
            "task_status": "completed" if status != "failed" else "failed",
            "document_id": document_id,
            "stage": stage,
            "status": status,
            "reason": reason,
            "pipeline_run_id": pipeline_run_id,
            "successors": successors,
            "result": result,
        }


register_task_handler(PIPELINE_TASK_TYPE, _pipeline_stage_handler)
