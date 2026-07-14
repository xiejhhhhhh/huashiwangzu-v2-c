import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-pipeline-batch")
REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

ValidationError = importlib.import_module("app.core.exceptions").ValidationError
pipeline_batch_service = importlib.import_module(
    "modules.knowledge.backend.services.pipeline_batch_service"
)
pipeline_service = importlib.import_module("modules.knowledge.backend.services.pipeline_service")


def _doc(document_id: int, *, owner_id: int = 4, extension: str = "pdf") -> SimpleNamespace:
    return SimpleNamespace(
        id=document_id,
        owner_id=owner_id,
        file_id=1000 + document_id,
        filename=f"batch-{document_id}.{extension}",
        extension=extension,
        total_pages=2,
        parse_status="done",
        raw_status="done",
        fusion_status="pending",
        profile_status="pending",
        graph_status="pending",
        relation_status="pending",
        deleted=False,
    )


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _BatchDb:
    def __init__(self, rows):
        self.rows = rows
        self.commit_count = 0

    async def execute(self, _statement):
        return _Rows(self.rows)

    async def commit(self):
        self.commit_count += 1


@pytest.mark.asyncio
async def test_stage_batch_defaults_to_dry_run_without_mutation(monkeypatch):
    db = _BatchDb([(_doc(10), SimpleNamespace())])
    monkeypatch.setattr(
        pipeline_batch_service,
        "_stage_eligibility",
        AsyncMock(return_value="eligible"),
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(pipeline_batch_service, "enqueue_pipeline_stage_task", enqueue)

    result = await pipeline_batch_service.enqueue_pipeline_stage_batch(
        db,
        actor_id=1,
        owner_id=4,
        stage="fusion",
    )

    assert result["dry_run"] is True
    assert result["actor_id"] == 1
    assert result["owner_id"] == 4
    assert result["candidate_document_ids"] == [10]
    assert result["would_enqueue"] == 1
    assert result["confirm_token"] == "ENQUEUE_KNOWLEDGE_STAGE_BATCH"
    assert db.commit_count == 0
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_stage_batch_rejects_unapproved_stage_and_missing_confirmation():
    db = _BatchDb([])

    with pytest.raises(ValidationError, match="raw_ocr"):
        await pipeline_batch_service.enqueue_pipeline_stage_batch(
            db,
            actor_id=1,
            owner_id=4,
            stage="relations",
        )

    with pytest.raises(ValidationError, match="confirm must be"):
        await pipeline_batch_service.enqueue_pipeline_stage_batch(
            db,
            actor_id=1,
            owner_id=4,
            stage="fusion",
            dry_run=False,
        )

    assert db.commit_count == 0


@pytest.mark.asyncio
async def test_stage_batch_apply_preserves_target_owner_and_admin_attribution(monkeypatch):
    doc = _doc(11)
    db = _BatchDb([(doc, SimpleNamespace())])
    monkeypatch.setattr(
        pipeline_batch_service,
        "_stage_eligibility",
        AsyncMock(return_value="eligible"),
    )
    enqueue = AsyncMock(return_value={"task_id": 88, "enqueued": True, "reason": "stage_created"})
    monkeypatch.setattr(pipeline_batch_service, "enqueue_pipeline_stage_task", enqueue)

    result = await pipeline_batch_service.enqueue_pipeline_stage_batch(
        db,
        actor_id=1,
        owner_id=4,
        stage="fusion",
        dry_run=False,
        confirm="ENQUEUE_KNOWLEDGE_STAGE_BATCH",
        audit_reason="valuable fusion pilot",
    )

    assert result["enqueued"] == 1
    assert result["already_in_flight"] == 0
    assert db.commit_count == 1
    enqueue.assert_awaited_once_with(
        db,
        doc,
        4,
        "fusion",
        priority=5,
        stop_after_stage="fusion",
        requested_by="user:1:admin-stage-batch",
        trigger="knowledge.admin.stage_batch",
        audit_reason="valuable fusion pilot",
        allow_degraded_parse=True,
    )


@pytest.mark.asyncio
async def test_stage_batch_reports_precise_skip_reasons(monkeypatch):
    docs = [_doc(12), _doc(13)]
    db = _BatchDb([(docs[0], SimpleNamespace()), (docs[1], SimpleNamespace())])
    eligibility = AsyncMock(side_effect=["upstream_not_ready", "stage_already_complete"])
    monkeypatch.setattr(pipeline_batch_service, "_stage_eligibility", eligibility)

    result = await pipeline_batch_service.enqueue_pipeline_stage_batch(
        db,
        actor_id=1,
        owner_id=4,
        stage="fusion",
    )

    assert result["would_enqueue"] == 0
    assert result["skipped_by_reason"] == {
        "stage_already_complete": 1,
        "upstream_not_ready": 1,
    }


@pytest.mark.asyncio
async def test_dispatcher_stops_after_requested_stage(monkeypatch):
    doc = _doc(14)
    task = SimpleNamespace(
        parameters=json.dumps({
            "schema_version": 1,
            "body": {
                "document_id": 14,
                "user_id": 4,
                "stage": "fusion",
                "stop_after_stage": "fusion",
                "audit_reason": "pilot",
            },
        }),
        document_id=14,
        creator_id=4,
        stage_key="fusion",
    )

    class Db:
        async def scalar(self, _statement):
            return doc

    finish = AsyncMock()
    successors = AsyncMock()
    monkeypatch.setattr(pipeline_service, "_finish_pipeline_run", finish)
    monkeypatch.setattr(pipeline_service, "settle_pipeline_stage_successors", successors)
    result = {"status": "done", "pipeline_run_id": 91}

    await pipeline_service._settle_pipeline_task(Db(), task, result)

    successors.assert_not_awaited()
    finish.assert_awaited_once()
    assert result["successors"] == []
    assert result["stopped_after_requested_stage"] is True
