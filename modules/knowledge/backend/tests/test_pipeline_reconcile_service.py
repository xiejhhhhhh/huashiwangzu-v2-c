from __future__ import annotations
# ruff: noqa: E402, I001

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-pipeline-reconcile")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.database import AsyncSessionLocal, init_db
from app.models.file import File
from modules.knowledge.backend.models import KbDocument, KbPipelineRun, KbPipelineStageRun
from modules.knowledge.backend.services.pipeline_reconcile_service import (
    apply_orphan_pipeline_run_reconcile,
    dry_run_orphan_pipeline_run_reconcile,
)

OWNER_ID = 1
_FRAMEWORK_READY = False


async def _ensure_framework_ready() -> None:
    global _FRAMEWORK_READY
    if _FRAMEWORK_READY:
        return
    await init_db()
    _FRAMEWORK_READY = True


async def _cleanup(doc_ids: list[int], file_ids: list[int]) -> None:
    async with AsyncSessionLocal() as db:
        for doc_id in doc_ids:
            await db.execute(text("DELETE FROM kb_pipeline_stage_runs WHERE document_id = :doc_id"), {"doc_id": doc_id})
            await db.execute(text("DELETE FROM kb_pipeline_runs WHERE document_id = :doc_id"), {"doc_id": doc_id})
            await db.execute(text("DELETE FROM kb_documents WHERE id = :doc_id"), {"doc_id": doc_id})
        for file_id in file_ids:
            await db.execute(text("DELETE FROM framework_file_items WHERE id = :file_id"), {"file_id": file_id})
        await db.commit()


async def _create_run_case(
    *,
    file_state: str,
    marker: str,
    task_id: int | None = None,
    diagnostics: dict | None = None,
) -> tuple[int, int, int | None]:
    await _ensure_framework_ready()
    async with AsyncSessionLocal() as db:
        file_id: int | None = None
        if file_state in {"live", "deleted"}:
            file = File(
                name=f"reconcile_{file_state}_{marker}",
                extension="txt",
                size=1,
                owner_id=OWNER_ID,
                storage_path=f"tests/reconcile_{marker}.txt",
                mime_type="text/plain",
                deleted=file_state == "deleted",
            )
            db.add(file)
            await db.flush()
            file_id = int(file.id)
        else:
            file_id = 990_000_000 + int(marker[:6], 16)

        doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=file_id,
            filename=f"reconcile_{marker}.txt",
            extension="txt",
            file_size=1,
            mime_type="text/plain",
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            deleted=False,
        )
        db.add(doc)
        await db.flush()

        run = KbPipelineRun(
            document_id=doc.id,
            owner_id=OWNER_ID,
            file_id=file_id,
            task_id=task_id,
            trigger="kb_pipeline_stage",
            status="running",
            diagnostics_json=diagnostics,
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()

        stage = KbPipelineStageRun(
            run_id=run.id,
            document_id=doc.id,
            owner_id=OWNER_ID,
            stage="raw",
            status="skipped",
            reason="source unavailable",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(stage)
        await db.commit()
        return int(doc.id), int(run.id), file_id if file_state in {"live", "deleted"} else None


@pytest.mark.asyncio
async def test_orphan_pipeline_reconcile_dry_run_lists_source_categories_and_latest_stage() -> None:
    marker = uuid.uuid4().hex[:8]
    doc_ids: list[int] = []
    file_ids: list[int] = []
    try:
        missing_doc_id, missing_run_id, _ = await _create_run_case(file_state="missing", marker=marker)
        deleted_doc_id, deleted_run_id, deleted_file_id = await _create_run_case(file_state="deleted", marker=marker)
        doc_ids.extend([missing_doc_id, deleted_doc_id])
        assert deleted_file_id is not None
        file_ids.append(deleted_file_id)

        async with AsyncSessionLocal() as db:
            result = await dry_run_orphan_pipeline_run_reconcile(
                db,
                run_ids=[missing_run_id, deleted_run_id],
            )

        assert result["matched"] == 2
        assert result["summary"] == {"source_file_missing": 1, "source_file_deleted": 1}
        assert result["would_change_by_category"] == {"source_file_missing": 1, "source_file_deleted": 1}
        items_by_category = {item["category"]: item for item in result["items"]}
        assert items_by_category["source_file_missing"]["would_set_status"] == "skipped"
        assert items_by_category["source_file_missing"]["would_set_reason"] == "source_file_missing"
        assert items_by_category["source_file_deleted"]["latest_stage"]["stage"] == "raw"
    finally:
        await _cleanup(doc_ids, file_ids)


@pytest.mark.asyncio
async def test_orphan_pipeline_reconcile_apply_source_missing_preserves_previous_diagnostics() -> None:
    marker = uuid.uuid4().hex[:8]
    doc_ids: list[int] = []
    try:
        doc_id, run_id, _ = await _create_run_case(
            file_state="missing",
            marker=marker,
            diagnostics={"original": {"kept": True}},
        )
        doc_ids.append(doc_id)

        async with AsyncSessionLocal() as db:
            result = await apply_orphan_pipeline_run_reconcile(db, run_ids=[run_id], dry_run=False)
            run = await db.get(KbPipelineRun, run_id)

        assert result["changed"] == 1
        assert result["changed_by_category"] == {"source_file_missing": 1}
        assert run is not None
        assert run.status == "skipped"
        assert run.reason == "source_file_missing"
        assert run.completed_at is not None
        assert run.diagnostics_json["original"] == {"kept": True}
        assert run.diagnostics_json["previous_status"] == "running"
        assert run.diagnostics_json["previous_diagnostics"] == {"original": {"kept": True}}
    finally:
        await _cleanup(doc_ids, [])


@pytest.mark.asyncio
async def test_orphan_pipeline_reconcile_rejects_live_without_task() -> None:
    marker = uuid.uuid4().hex[:8]
    doc_ids: list[int] = []
    file_ids: list[int] = []
    try:
        doc_id, run_id, file_id = await _create_run_case(file_state="live", marker=marker)
        doc_ids.append(doc_id)
        assert file_id is not None
        file_ids.append(file_id)

        async with AsyncSessionLocal() as db:
            result = await apply_orphan_pipeline_run_reconcile(db, run_ids=[run_id], dry_run=False)
            run = await db.get(KbPipelineRun, run_id)

        assert result["changed"] == 0
        assert result["skipped"] == 1
        assert result["skipped_by_category"] == {"live_without_task": 1}
        assert run is not None
        assert run.status == "running"
        assert run.completed_at is None
    finally:
        await _cleanup(doc_ids, file_ids)


@pytest.mark.asyncio
async def test_orphan_pipeline_reconcile_ignores_task_id_not_null() -> None:
    marker = uuid.uuid4().hex[:8]
    doc_ids: list[int] = []
    try:
        doc_id, run_id, _ = await _create_run_case(file_state="missing", marker=marker, task_id=12345)
        doc_ids.append(doc_id)

        async with AsyncSessionLocal() as db:
            result = await apply_orphan_pipeline_run_reconcile(db, run_ids=[run_id], dry_run=False)
            run = await db.get(KbPipelineRun, run_id)

        assert result["matched"] == 0
        assert result["changed"] == 0
        assert run is not None
        assert run.status == "running"
        assert run.completed_at is None
    finally:
        await _cleanup(doc_ids, [])
