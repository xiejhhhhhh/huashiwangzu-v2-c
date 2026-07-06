"""Stable analysis artifact ledger helpers for the knowledge pipeline."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.database import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbAnalysisArtifact
from .prompt_utils import TENTITY, TFUSION, TPROFILE, TRAW_OCR, TRAW_VISION, load_prompt

logger = logging.getLogger("v2.knowledge").getChild("artifacts")

ARTIFACT_SCHEMA_VERSION = "knowledge_artifact_v1"

STAGE_SCHEMA_VERSIONS: dict[str, str] = {
    "source_file": "source_file_v1",
    "raw": "raw_v1",
    "fusion": "fusion_v1",
    "profile": "profile_v1",
    "graph": "entity_graph_v1",
    "relations": "relations_v1",
    "pause": "pause_v1",
}

STAGE_PROMPTS: dict[str, tuple[str, ...]] = {
    "raw": (TRAW_OCR, TRAW_VISION),
    "fusion": (TFUSION,),
    "profile": (TPROFILE,),
    "graph": (TENTITY,),
}


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def stable_json_dumps(value: Any) -> str:
    """Serialize values deterministically for content hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json_dumps(value).encode("utf-8")).hexdigest()


def prompt_hash(prompt_text: str) -> str:
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def stage_schema_version(stage: str) -> str:
    return STAGE_SCHEMA_VERSIONS.get(stage, ARTIFACT_SCHEMA_VERSION)


async def resolve_stage_prompt_hash(db: AsyncSession | None, stage: str) -> str | None:
    """Hash the exact prompt text used by a stage when the stage is prompt-backed."""
    template_names = STAGE_PROMPTS.get(stage)
    if not template_names:
        return None
    prompts = {}
    for template_name in template_names:
        prompts[template_name] = await load_prompt(db, template_name)
    return stable_hash(prompts)


def build_input_hash(
    *,
    stage: str,
    document_id: int,
    file_id: int | None,
    source_artifact_ids: list[int] | None = None,
    upstream_hashes: dict[str, str] | None = None,
    extra: dict | None = None,
) -> str:
    return stable_hash({
        "stage": stage,
        "document_id": document_id,
        "file_id": file_id,
        "source_artifact_ids": source_artifact_ids or [],
        "upstream_hashes": upstream_hashes or {},
        "extra": extra or {},
    })


def build_output_hash(*, stage: str, status: str, payload: Any) -> str:
    return stable_hash({
        "stage": stage,
        "status": status,
        "payload": payload,
    })


def _first_model_value(result: dict | None, key: str) -> str | None:
    if not isinstance(result, dict):
        return None
    diagnostics = result.get("model_diagnostics")
    if isinstance(diagnostics, list):
        for item in diagnostics:
            if isinstance(item, dict) and item.get(key):
                return str(item[key])
    if isinstance(diagnostics, dict) and diagnostics.get(key):
        return str(diagnostics[key])
    return None


def model_profile_from_result(result: dict | None) -> str | None:
    return _first_model_value(result, "requested_profile")


def model_used_from_result(result: dict | None) -> str | None:
    return _first_model_value(result, "selected_profile") or _first_model_value(result, "model_used")


async def record_analysis_artifact(
    *,
    owner_id: int,
    document_id: int,
    file_id: int | None,
    stage: str,
    status: str,
    unit_type: str = "document",
    unit_key: str = "document",
    task_id: int | None = None,
    pipeline_run_id: int | None = None,
    source_artifact_ids: list[int] | None = None,
    input_hash: str = "",
    output_hash: str = "",
    prompt_hash_value: str | None = None,
    model_profile: str | None = None,
    model_used: str | None = None,
    schema_version: str | None = None,
    preprocess_version: str | None = None,
    reason: str = "",
    diagnostics: dict | None = None,
    metrics: dict | None = None,
    duration_ms: int | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    session_factory: Any | None = None,
) -> int | None:
    """Persist an analysis artifact in a separate best-effort DB session."""
    session_ref = None
    factory = session_factory or AsyncSessionLocal
    try:
        async with factory() as session:
            session_ref = session
            record = KbAnalysisArtifact(
                owner_id=owner_id,
                document_id=document_id,
                file_id=file_id,
                task_id=task_id,
                pipeline_run_id=pipeline_run_id,
                stage=stage,
                unit_type=unit_type,
                unit_key=unit_key,
                source_artifact_ids=source_artifact_ids or [],
                input_hash=input_hash,
                output_hash=output_hash,
                prompt_hash=prompt_hash_value,
                model_profile=model_profile,
                model_used=model_used,
                schema_version=schema_version or stage_schema_version(stage),
                preprocess_version=preprocess_version,
                status=status,
                reason=reason or None,
                diagnostics_json=diagnostics or {},
                metrics_json=metrics or {},
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=completed_at or datetime.now(timezone.utc),
            )
            session.add(record)
            await session.flush()
            artifact_id = int(record.id)
            await session.commit()
            return artifact_id
    except Exception as exc:
        if session_ref is not None:
            await session_ref.rollback()
        logger.warning(
            "Analysis artifact write skipped doc_id=%d stage=%s status=%s: %s",
            document_id,
            stage,
            status,
            exc,
        )
        return None
