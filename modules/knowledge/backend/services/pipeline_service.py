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
from app.models.file import File
from app.models.system import SystemTaskQueue
from app.services.task_dispatcher import (
    TaskDefinition,
    publish_task,
    register_task_definition,
    register_task_settlement_handler,
    unpack_task_parameters,
)
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
from .document_service import (
    NON_CONTENT_FILE_REASONS,
    SOURCE_UNAVAILABLE_REASONS,
    document_deep_pipeline_complete,
    document_parse_allows_search,
    mark_document_non_content_skipped,
    mark_document_source_unavailable,
)
from .model_routing import (
    is_model_stage,
    pause_model_stage_queue,
    record_model_rate_limit,
    resolve_knowledge_pipeline_priority,
    should_pause_after_result,
)
from .page_asset_service import page_assets_complete
from .pipeline_stages import run_pipeline_stage
from .source_file_state import classify_non_content_file, get_source_file_availability, raise_if_source_unavailable
from .stage_result_cache_service import delete_stage_result_cache, write_stage_result_cache

logger = logging.getLogger("v2.knowledge").getChild("pipeline")

PIPELINE_TASK_TYPE = "kb_pipeline_stage"
PIPELINE_MAX_RETRIES = 5
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
    "raw_ocr": "vision_analysis",
    "raw_vision": "vision_analysis",
    "fusion": "llm_analysis",
    "profile": "llm_analysis",
    "cognitive_index": "derived_index",
    "graph": "llm_analysis",
    "relations": "relation_build",
}
STAGE_RESOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "source_validate": {"cpu_cores": 0.1, "rss_estimate_mb": 128, "timeout_seconds": 300},
    "parse_index": {"cpu_cores": 1.0, "rss_estimate_mb": 1536, "timeout_seconds": 1200},
    "raw_text": {"cpu_cores": 0.5, "rss_estimate_mb": 512, "timeout_seconds": 900},
    "page_render": {"cpu_cores": 1.0, "rss_estimate_mb": 2048, "timeout_seconds": 1200},
    "raw_ocr": {"cloud": True, "provider_key": "knowledge_vlm", "rss_estimate_mb": 256, "timeout_seconds": 900},
    "raw_vision": {"cloud": True, "provider_key": "knowledge_vlm", "rss_estimate_mb": 256, "timeout_seconds": 900},
    "fusion": {"cloud": True, "provider_key": "knowledge_llm", "rss_estimate_mb": 256, "timeout_seconds": 1800},
    "profile": {"cloud": True, "provider_key": "knowledge_llm", "rss_estimate_mb": 256, "timeout_seconds": 1800},
    "cognitive_index": {"cpu_cores": 0.5, "rss_estimate_mb": 768, "timeout_seconds": 1200},
    "graph": {"cloud": True, "provider_key": "knowledge_llm", "rss_estimate_mb": 256, "timeout_seconds": 3600},
    "relations": {"cpu_cores": 0.5, "rss_estimate_mb": 1024, "timeout_seconds": 1800},
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


def _truncate_diagnostic_text(value: object, *, limit: int = 2000) -> str:
    text_value = str(value or "").strip()
    return text_value[:limit]


def _exception_chain_diagnostics(exc: BaseException) -> list[dict[str, Any]]:
    """Preserve wrapped parser/converter causes without emitting unbounded text."""
    chain: list[dict[str, Any]] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        item: dict[str, Any] = {
            "exception_type": type(current).__name__,
            "message": _truncate_diagnostic_text(current),
        }
        conversion_diagnostics = getattr(current, "diagnostics", None)
        if isinstance(conversion_diagnostics, dict):
            item["conversion"] = _json_safe(conversion_diagnostics)
        chain.append(item)
        current = current.__cause__ or current.__context__
    return chain


async def _build_failure_diagnostics(
    db: AsyncSession,
    *,
    doc: KbDocument,
    stage: str,
    task_id: int | None,
    pipeline_run_id: int | None,
    exc: BaseException,
) -> dict[str, Any]:
    """Build a persisted, privacy-safe failure envelope for every pipeline stage."""
    source = await db.get(File, int(doc.file_id))
    return {
        "schema_version": "knowledge_pipeline_failure_v1",
        "task_id": task_id,
        "pipeline_run_id": pipeline_run_id,
        "document_id": int(doc.id),
        "file_id": int(doc.file_id),
        "stage": stage,
        "lane": STAGE_LANE_KEYS.get(stage),
        "source": {
            "filename": getattr(doc, "filename", None),
            "extension": getattr(doc, "extension", None),
            "mime_type": getattr(doc, "mime_type", None),
            "file_size": getattr(doc, "file_size", None),
            "storage_path": source.storage_path if source is not None else None,
            "md5_hash": source.md5_hash if source is not None else None,
        },
        "exception_chain": _exception_chain_diagnostics(exc),
    }


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
    stop_after_stage: str | None = None,
    requested_by: str | None = None,
    trigger: str = "knowledge.pipeline.successor",
    audit_reason: str = "",
    allow_degraded_parse: bool = False,
) -> dict:
    """Enqueue one DAG stage, deduping active work for the same document/stage."""
    if stage not in PIPELINE_STAGES:
        raise ValueError(f"Unknown knowledge pipeline stage: {stage}")
    if stop_after_stage is not None and stop_after_stage not in PIPELINE_STAGES:
        raise ValueError(f"Unknown knowledge pipeline stop stage: {stop_after_stage}")
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
        "stop_after_stage": stop_after_stage,
        "audit_reason": audit_reason.strip(),
        "allow_degraded_parse": bool(allow_degraded_parse),
    }
    task = await publish_task(
        db,
        task_type=PIPELINE_TASK_TYPE,
        module="knowledge",
        owner_id=user_id,
        body=payload,
        requested_by=requested_by or f"user:{user_id}",
        trigger=trigger,
        priority=resolved_priority,
        max_retries=PIPELINE_MAX_RETRIES,
        document_id=int(doc.id),
        stage_key=stage,
        lane_key=STAGE_LANE_KEYS.get(stage, "knowledge"),
        ready_status="ready",
        dependency_key=f"knowledge:{int(doc.id)}:{stage}",
        resource_profile=STAGE_RESOURCE_PROFILES.get(stage),
    )
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
    if safe_result.get("failure_diagnostics"):
        diagnostics["failure_diagnostics"] = safe_result.get("failure_diagnostics")

    try:
        prompt_hash_value = await resolve_stage_prompt_hash(db, stage)
    except Exception as exc:
        logger.warning("Prompt hash skipped doc_id=%d stage=%s: %s", int(doc.id), stage, exc)
        prompt_hash_value = None
    source_revision = None
    if hasattr(db, "scalar"):
        source_revision = await db.scalar(select(File.md5_hash).where(File.id == int(doc.file_id)))
    input_hash = build_input_hash(
        stage=stage,
        document_id=int(doc.id),
        file_id=int(doc.file_id),
        extra={
            "source_revision": str(source_revision or ""),
            "stage_schema_version": stage_schema_version(stage),
            "prompt_hash": prompt_hash_value,
            "model_profile": model_profile_from_result(safe_result),
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


async def _ready_for_fusion(
    db: AsyncSession,
    doc: KbDocument,
    *,
    allow_degraded_parse: bool = False,
) -> bool:
    parse_ready = _parse_index_ready(doc)
    if allow_degraded_parse and not parse_ready:
        parse_ready = (
            str(getattr(doc, "parse_status", "") or "").lower() == "degraded"
            and int(getattr(doc, "total_chunks", 0) or 0) > 0
        )
    return parse_ready and await _raw_complete(db, doc)


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


async def settle_pipeline_stage_successors(
    db: AsyncSession,
    *,
    doc: KbDocument,
    user_id: int,
    completed_stage: str,
    pipeline_run_id: int | None,
    force_raw: bool = False,
    force_fusion: bool = False,
) -> list[dict]:
    """Publish stages unlocked by a committed stage result.

    This is the dispatcher settlement boundary: a future dispatcher may call it
    after persisting a stage outcome without needing to duplicate DAG rules.
    """
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


# Compatibility for existing callers and focused semantics tests.
_enqueue_successors = settle_pipeline_stage_successors


async def _run_stage(
    db: AsyncSession,
    *,
    doc: KbDocument,
    user_id: int,
    stage: str,
    task_id: int | None = None,
    force_raw: bool = False,
    force_fusion: bool = False,
    allow_degraded_parse: bool = False,
) -> dict:
    async def ready_for_fusion(stage_db: AsyncSession, stage_doc: KbDocument) -> bool:
        return await _ready_for_fusion(
            stage_db,
            stage_doc,
            allow_degraded_parse=allow_degraded_parse,
        )

    return await run_pipeline_stage(
        stage,
        db=db,
        doc=doc,
        user_id=user_id,
        task_id=task_id,
        force_raw=force_raw,
        force_fusion=force_fusion,
        ready_for_fusion=ready_for_fusion,
        ready_for_cognitive_index=_ready_for_cognitive_index,
        cognitive_index_complete=_cognitive_index_complete,
    )


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
    allow_degraded_parse = bool(params.get("allow_degraded_parse", False))
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
                    allow_degraded_parse=allow_degraded_parse,
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
                failure_diagnostics = await _build_failure_diagnostics(
                    db,
                    doc=doc,
                    stage=stage,
                    task_id=task_id,
                    pipeline_run_id=pipeline_run_id,
                    exc=exc,
                )
                result = {
                    "document_id": document_id,
                    "status": "failed",
                    "error": _truncate_diagnostic_text(exc),
                    "failure_diagnostics": failure_diagnostics,
                }
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
                logger.exception(
                    "Knowledge pipeline stage failed task_id=%s document_id=%d file_id=%d stage=%s diagnostics=%s",
                    task_id,
                    document_id,
                    file_id,
                    stage,
                    json.dumps(failure_diagnostics, ensure_ascii=False, default=str),
                )

        status, reason = _stage_status_from_result(result)
        if status == "failed" and not result.get("failure_diagnostics"):
            failure_diagnostics = await _build_failure_diagnostics(
                db,
                doc=doc,
                stage=stage,
                task_id=task_id,
                pipeline_run_id=pipeline_run_id,
                exc=RuntimeError(reason),
            )
            failure_diagnostics["stage_result"] = {
                key: _json_safe(result.get(key))
                for key in ("failed_pages", "pages", "assets", "materialized", "reused", "total_pages", "timing")
                if key in result
            }
            result["failure_diagnostics"] = failure_diagnostics
            logger.error(
                "Knowledge pipeline stage returned failure task_id=%s document_id=%d file_id=%d stage=%s diagnostics=%s",
                task_id,
                document_id,
                file_id,
                stage,
                json.dumps(failure_diagnostics, ensure_ascii=False, default=str),
            )
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
                # The handler owns stage work only. The Dispatcher invokes the
                # settlement callback after this result is durable and fenced.
                result["dispatcher_settlement"] = "required"
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


async def _settle_pipeline_task(
    db: AsyncSession,
    task: SystemTaskQueue,
    result: dict[str, Any],
) -> None:
    """Publish DAG successors in the Dispatcher's fenced settlement transaction."""
    status, reason = _stage_status_from_result(result)
    if status not in {"done", "degraded", "skipped"}:
        return
    if should_pause_after_result(result) or (status == "skipped" and _is_terminal_skip(reason)):
        return
    params = unpack_task_parameters(task.parameters)
    document_id = int(task.document_id or params.get("document_id") or 0)
    if document_id <= 0:
        return
    doc = await db.scalar(select(KbDocument).where(KbDocument.id == document_id))
    if doc is None or doc.deleted:
        return
    user_id = int(params.get("user_id") or task.creator_id or doc.owner_id)
    stage = str(task.stage_key or params.get("stage") or ROOT_STAGE)
    pipeline_run_id = int(result.get("pipeline_run_id") or params.get("pipeline_run_id") or 0) or None
    stop_after_stage = str(params.get("stop_after_stage") or "").strip()
    if stop_after_stage and stage == stop_after_stage:
        await _finish_pipeline_run(
            db,
            pipeline_run_id,
            "degraded" if status == "degraded" else "done",
            reason=reason if status == "degraded" else "stopped_after_requested_stage",
            diagnostics={
                "last_stage": stage,
                "stop_after_stage": stop_after_stage,
                "stopped_after_requested_stage": True,
                "audit_reason": str(params.get("audit_reason") or "").strip(),
            },
        )
        result["successors"] = []
        result["stopped_after_requested_stage"] = True
        return
    successors = await settle_pipeline_stage_successors(
        db,
        doc=doc,
        user_id=user_id,
        completed_stage=stage,
        pipeline_run_id=pipeline_run_id,
        force_raw=bool(params.get("force_raw", False)),
        force_fusion=bool(params.get("force_fusion", False)),
    )
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
    result["successors"] = successors


register_task_definition(TaskDefinition(task_type=PIPELINE_TASK_TYPE, default_lane="local_preprocess", rss_estimate_mb=512))
register_task_handler(PIPELINE_TASK_TYPE, _pipeline_stage_handler)
register_task_settlement_handler(PIPELINE_TASK_TYPE, _settle_pipeline_task)
