"""Dry-run rerun planning for knowledge pipeline stages."""
from __future__ import annotations

from app.core.exceptions import NotFound, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbAnalysisArtifact, KbDocument

STAGE_ORDER = ("raw", "fusion", "profile", "graph", "relations")
STAGE_ALIASES = {
    "entity": "graph",
    "entities": "graph",
    "relation": "relations",
}
STAGE_DEPS = {
    "raw": ("source_file",),
    "fusion": ("raw",),
    "profile": ("fusion",),
    "graph": ("fusion",),
    "relations": ("profile", "graph"),
}
PROMPT_BACKED_STAGES = {"raw", "fusion", "profile", "graph"}
MODEL_BACKED_STAGES = {"raw", "fusion", "profile", "graph"}
RERUN_REASONS = {
    "prompt_changed",
    "schema_changed",
    "model_changed",
    "source_changed",
    "vlm_preprocess_changed",
    "manual_failed_retry",
}
FAILED_ARTIFACT_STATUSES = {"failed", "degraded", "paused", "stale"}
MODEL_CALL_STAGES = {"raw", "fusion", "profile", "graph"}


def normalize_stage(stage: str | None) -> str | None:
    if not stage:
        return None
    normalized = stage.strip().lower()
    return STAGE_ALIASES.get(normalized, normalized)


def downstream_stages(start_stages: list[str]) -> list[str]:
    planned = set(start_stages)
    changed = True
    while changed:
        changed = False
        for stage in STAGE_ORDER:
            if stage in planned:
                continue
            if any(dep in planned for dep in STAGE_DEPS[stage]):
                planned.add(stage)
                changed = True
    return [stage for stage in STAGE_ORDER if stage in planned]


def starting_stages_for_reason(reason: str, stage: str | None) -> list[str]:
    if reason not in RERUN_REASONS:
        raise ValidationError(f"Unsupported rerun reason: {reason}")
    normalized_stage = normalize_stage(stage)
    if normalized_stage is not None and normalized_stage not in STAGE_ORDER:
        raise ValidationError(f"Unsupported rerun stage: {stage}")
    if normalized_stage is not None:
        return [normalized_stage]
    if reason == "prompt_changed":
        return ["raw", "fusion", "profile", "graph"]
    if reason == "model_changed":
        return [stage_name for stage_name in STAGE_ORDER if stage_name in MODEL_BACKED_STAGES]
    if reason in {"source_changed", "vlm_preprocess_changed", "schema_changed"}:
        return ["raw"]
    if reason == "manual_failed_retry":
        return []
    return []


async def _latest_artifact_by_stage(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
) -> dict[str, KbAnalysisArtifact]:
    artifacts: dict[str, KbAnalysisArtifact] = {}
    for stage in STAGE_ORDER:
        artifact = await db.scalar(
            select(KbAnalysisArtifact)
            .where(
                KbAnalysisArtifact.document_id == document_id,
                KbAnalysisArtifact.owner_id == owner_id,
                KbAnalysisArtifact.stage == stage,
            )
            .order_by(KbAnalysisArtifact.id.desc())
            .limit(1)
        )
        if artifact is not None:
            artifacts[stage] = artifact
    return artifacts


async def _artifact_counts_by_stage(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
) -> dict[str, int]:
    result = await db.execute(
        select(KbAnalysisArtifact.stage, func.count(KbAnalysisArtifact.id))
        .where(
            KbAnalysisArtifact.document_id == document_id,
            KbAnalysisArtifact.owner_id == owner_id,
            KbAnalysisArtifact.stage.in_(STAGE_ORDER),
        )
        .group_by(KbAnalysisArtifact.stage)
    )
    return {str(stage): int(count) for stage, count in result.all()}


def _first_failed_stage(latest_artifacts: dict[str, KbAnalysisArtifact], doc: KbDocument) -> str | None:
    for stage in STAGE_ORDER:
        artifact = latest_artifacts.get(stage)
        if artifact is not None and artifact.status in FAILED_ARTIFACT_STATUSES:
            return stage
        status_field = "relation_status" if stage == "relations" else f"{stage}_status"
        status = str(getattr(doc, status_field, "") or "").lower()
        if status in FAILED_ARTIFACT_STATUSES:
            return stage
    return None


async def plan_pipeline_rerun(
    db: AsyncSession,
    *,
    document_id: int,
    owner_id: int,
    reason: str,
    stage: str | None = None,
) -> dict:
    """Return a dry-run rerun plan without mutating pipeline or artifacts."""
    doc = await db.scalar(
        select(KbDocument).where(
            KbDocument.id == document_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted.is_(False),
        )
    )
    if doc is None:
        raise NotFound("Document not found")

    normalized_reason = reason.strip().lower()
    latest_artifacts = await _latest_artifact_by_stage(db, document_id, owner_id)
    artifact_counts = await _artifact_counts_by_stage(db, document_id, owner_id)
    starts = starting_stages_for_reason(normalized_reason, stage)
    if normalized_reason == "manual_failed_retry" and not starts:
        failed_stage = _first_failed_stage(latest_artifacts, doc)
        starts = [failed_stage] if failed_stage else []
    planned_stage_names = downstream_stages(starts) if starts else []

    stages = []
    for planned_stage in planned_stage_names:
        artifact = latest_artifacts.get(planned_stage)
        status_field = "relation_status" if planned_stage == "relations" else f"{planned_stage}_status"
        stages.append({
            "stage": planned_stage,
            "reason": normalized_reason,
            "requires_model": planned_stage in MODEL_CALL_STAGES,
            "dependencies": list(STAGE_DEPS[planned_stage]),
            "current_status": str(getattr(doc, status_field, "pending") or "pending"),
            "latest_artifact_id": int(artifact.id) if artifact is not None else None,
            "latest_artifact_status": artifact.status if artifact is not None else None,
            "latest_input_hash": artifact.input_hash if artifact is not None else None,
            "latest_output_hash": artifact.output_hash if artifact is not None else None,
            "artifact_count": artifact_counts.get(planned_stage, 0),
        })

    return {
        "document_id": document_id,
        "owner_id": owner_id,
        "dry_run": True,
        "will_mutate": False,
        "reason": normalized_reason,
        "requested_stage": normalize_stage(stage),
        "start_stages": starts,
        "planned_stages": planned_stage_names,
        "stages": stages,
        "model_stage_count": sum(1 for item in stages if item["requires_model"]),
        "message": "No failed stage found" if normalized_reason == "manual_failed_retry" and not starts else "",
    }
