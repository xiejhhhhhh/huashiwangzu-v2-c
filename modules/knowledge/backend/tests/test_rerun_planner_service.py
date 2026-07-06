"""Tests for knowledge pipeline rerun dry-run planning."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, or_, select, text

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-rerun-planner")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.database import AsyncSessionLocal

from modules.knowledge.backend.init_db import ensure_kb_tables, ensure_migration_columns
from modules.knowledge.backend.models import KbAnalysisArtifact, KbDocument
from modules.knowledge.backend.services.rerun_planner_service import plan_pipeline_rerun

OWNER_ID = 1
TEST_FILE_ID = 910_000_000


async def _cleanup_stale_test_documents(db) -> None:
    result = await db.execute(
        select(KbDocument.id).where(
            or_(
                KbDocument.file_id == TEST_FILE_ID,
                KbDocument.filename.like("rerun-plan-%"),
            )
        )
    )
    for document_id in result.scalars().all():
        await db.execute(
            text("DELETE FROM kb_analysis_artifacts WHERE document_id = :document_id"),
            {"document_id": int(document_id)},
        )
        await db.execute(
            text("DELETE FROM kb_documents WHERE id = :document_id"),
            {"document_id": int(document_id)},
        )
    await db.commit()


async def _ensure_schema() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_kb_tables(db)
        await ensure_migration_columns(db)
        await _cleanup_stale_test_documents(db)


async def _cleanup(document_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM kb_analysis_artifacts WHERE document_id = :document_id"),
            {"document_id": document_id},
        )
        await db.execute(text("DELETE FROM kb_documents WHERE id = :document_id"), {"document_id": document_id})
        await db.commit()


async def _create_document_with_artifacts(fusion_status: str = "done") -> int:
    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=TEST_FILE_ID,
            filename=f"rerun-plan-{marker}.txt",
            extension="txt",
            file_size=1,
            mime_type="text/plain",
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status=fusion_status,
            profile_status="done",
            graph_status="done",
            relation_status="done",
            total_chunks=1,
            total_pages=1,
            deleted=False,
        )
        db.add(doc)
        await db.flush()
        document_id = int(doc.id)
        for stage, status in (
            ("raw", "done"),
            ("fusion", fusion_status),
            ("profile", "done"),
            ("graph", "done"),
            ("relations", "done"),
        ):
            db.add(KbAnalysisArtifact(
                owner_id=OWNER_ID,
                document_id=document_id,
                file_id=TEST_FILE_ID,
                stage=stage,
                status=status,
                input_hash=f"{stage}-input-{marker}",
                output_hash=f"{stage}-output-{marker}",
                schema_version=f"{stage}_v1",
            ))
        await db.commit()
        return document_id


@pytest.mark.asyncio
async def test_rerun_plan_expands_downstream_from_requested_stage() -> None:
    await _ensure_schema()
    document_id = await _create_document_with_artifacts()
    try:
        async with AsyncSessionLocal() as db:
            before_count = await db.scalar(
                select(func.count(KbAnalysisArtifact.id)).where(KbAnalysisArtifact.document_id == document_id)
            )
            plan = await plan_pipeline_rerun(
                db,
                document_id=document_id,
                owner_id=OWNER_ID,
                reason="prompt_changed",
                stage="profile",
            )
            after_count = await db.scalar(
                select(func.count(KbAnalysisArtifact.id)).where(KbAnalysisArtifact.document_id == document_id)
            )

        assert plan["dry_run"] is True
        assert plan["will_mutate"] is False
        assert plan["start_stages"] == ["profile"]
        assert plan["planned_stages"] == ["profile", "relations"]
        assert [item["stage"] for item in plan["stages"]] == ["profile", "relations"]
        assert plan["stages"][0]["requires_model"] is True
        assert plan["stages"][1]["requires_model"] is False
        assert before_count == after_count == 5
    finally:
        await _cleanup(document_id)


@pytest.mark.asyncio
async def test_manual_failed_retry_starts_from_first_failed_artifact() -> None:
    await _ensure_schema()
    document_id = await _create_document_with_artifacts(fusion_status="failed")
    try:
        async with AsyncSessionLocal() as db:
            plan = await plan_pipeline_rerun(
                db,
                document_id=document_id,
                owner_id=OWNER_ID,
                reason="manual_failed_retry",
            )

        assert plan["start_stages"] == ["fusion"]
        assert plan["planned_stages"] == ["fusion", "profile", "graph", "relations"]
        assert plan["stages"][0]["latest_artifact_status"] == "failed"
        assert plan["message"] == ""
    finally:
        await _cleanup(document_id)
