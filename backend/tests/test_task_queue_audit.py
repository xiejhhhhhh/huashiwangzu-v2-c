"""Tests for task_queue_audit_service.py — classification, reconcile, debt tracking."""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.database import AsyncSessionLocal
from app.models.system import SystemTaskQueue
from app.routers.tasks import worker_status
from app.services import task_queue_audit_service as audit
from app.services.task_debt_governance_service import govern_task_queue_debt
from app.services.task_queue_audit_service import reconcile_orphan_running, reconcile_stale_pending
from sqlalchemy import delete, text


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(SystemTaskQueue).where(SystemTaskQueue.task_type.like(f"test_audit_{marker}%"))
        )
        await db.execute(
            delete(SystemTaskQueue).where(SystemTaskQueue.parameters.like(f"%{marker}%"))
        )
        await db.execute(
            text("DELETE FROM kb_documents WHERE filename LIKE :marker"),
            {"marker": f"%{marker}%"},
        )
        await db.execute(
            text("DELETE FROM framework_file_items WHERE name LIKE :marker"),
            {"marker": f"%{marker}%"},
        )
        await db.commit()


async def _create_task(
    task_type: str,
    status: str,
    *,
    started_at: datetime | None = None,
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
    error_message: str | None = None,
    retry_count: int = 0,
    max_retries: int = 3,
    scheduled_at: datetime | None = None,
    module: str = "test",
    parameters: dict | None = None,
    result: dict | None = None,
) -> int:
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        task = SystemTaskQueue(
            task_type=task_type,
            parameters=json.dumps(parameters or {"marker": task_type}),
            status=status,
            priority=0,
            module=module,
            retry_count=retry_count,
            max_retries=max_retries,
            started_at=started_at,
            created_at=created_at or now,
            completed_at=completed_at,
            error_message=error_message,
            scheduled_at=scheduled_at,
            result=json.dumps(result, ensure_ascii=False) if result is not None else None,
        )
        db.add(task)
        await db.commit()
        return task.id


async def _create_file_and_document(
    marker: str,
    *,
    file_deleted: bool = False,
    document_deleted: bool = False,
    missing_file_row: bool = False,
) -> int:
    async with AsyncSessionLocal() as db:
        file_id = 999_000_000
        if not missing_file_row:
            file_row = await db.execute(
                text(
                    """
                    INSERT INTO framework_file_items
                        (name, extension, size, owner_id, storage_path, mime_type, ref_count, deleted, created_at, updated_at)
                    VALUES
                        (:name, 'txt', 12, 1, :storage_path, 'text/plain', 1, :deleted, now(), now())
                    RETURNING id
                    """
                ),
                {
                    "name": f"test_audit_{marker}_file",
                    "storage_path": f"tests/test_audit_{marker}.txt",
                    "deleted": file_deleted,
                },
            )
            file_id = int(file_row.scalar_one())

        doc_row = await db.execute(
            text(
                """
                INSERT INTO kb_documents
                    (owner_id, file_id, filename, extension, file_size, mime_type,
                     parse_status, vector_status, raw_status, fusion_status,
                     total_chunks, total_pages, deleted, created_at, updated_at)
                VALUES
                    (1, :file_id, :filename, 'txt', 12, 'text/plain',
                     'error', 'pending', 'pending', 'pending',
                     0, 0, :deleted, now(), now())
                RETURNING id
                """
            ),
            {
                "file_id": file_id,
                "filename": f"test_audit_{marker}_doc.txt",
                "deleted": document_deleted,
            },
        )
        await db.commit()
        return int(doc_row.scalar_one())


@pytest.mark.asyncio
async def test_audit_historical_debt_total_is_not_sample_limited() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            baseline = await audit.audit_task_queue(db)

        baseline_total = baseline["historical_debt_total"]
        async with AsyncSessionLocal() as db:
            for index in range(501):
                db.add(
                    SystemTaskQueue(
                        task_type=f"test_audit_{marker}_{index}",
                        parameters=json.dumps({"marker": marker, "index": index}),
                        status="failed",
                        priority=0,
                        module="test",
                        retry_count=0,
                        max_retries=3,
                        created_at=now - timedelta(hours=3),
                        completed_at=now - timedelta(hours=2),
                        error_message="historical debt sample-limit regression",
                    )
                )
            await db.commit()

        async with AsyncSessionLocal() as db:
            audit_result = await audit.audit_task_queue(db)

        assert audit_result["historical_debt_total"] >= baseline_total + 501
        assert audit_result["classification"]["historical_failed_debt_count"] >= baseline_total + 501
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_audit_classifies_recent_vs_historical_failed() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=2)
        await _create_task(
            f"test_audit_{marker}_recent", "failed",
            completed_at=now - timedelta(minutes=30),
            error_message="recent failure",
        )
        await _create_task(
            f"test_audit_{marker}_old", "failed",
            completed_at=old,
            error_message="old debt",
        )

        async with AsyncSessionLocal() as db:
            audit_result = await audit.audit_task_queue(db)

        assert audit_result["recent_failed_count"] >= 1, "recent failure should be visible"
        assert audit_result["historical_debt_total"] >= 1, "old failure should be historical debt"
        assert audit_result["classification"]["historical_failed_debt_count"] >= 1
        assert audit_result["classification"]["recent_failed_count"] >= 1
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_worker_status_oldest_waiting_seconds_ignores_future_scheduled_pending() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        await _create_task(
            f"test_audit_{marker}_future",
            "pending",
            created_at=now - timedelta(days=365 * 50),
            scheduled_at=now + timedelta(days=1),
        )
        await _create_task(
            f"test_audit_{marker}_due",
            "pending",
            created_at=now - timedelta(seconds=5),
            scheduled_at=now - timedelta(seconds=1),
        )

        async with AsyncSessionLocal() as db:
            response = await worker_status(db=db, user=None)

        assert response.data is not None
        assert response.data.oldest_waiting_seconds is not None
        assert response.data.oldest_waiting_seconds < 365 * 24 * 60 * 60
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_audit_classifies_stale_pending() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        await _create_task(
            f"test_audit_{marker}_fresh", "pending",
            created_at=now - timedelta(minutes=5),
        )
        await _create_task(
            f"test_audit_{marker}_stale", "pending",
            created_at=now - timedelta(hours=2),
        )

        async with AsyncSessionLocal() as db:
            audit_result = await audit.audit_task_queue(db)

        cls = audit_result["classification"]
        assert cls["actionable_pending_count"] >= 1, "fresh pending should be actionable"
        assert cls["stale_pending_debt_count"] >= 1, "stale pending should be debt"
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_reconcile_stale_pending_marks_as_failed() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        task_id = await _create_task(
            f"test_audit_{marker}_stale_recon", "pending",
            created_at=now - timedelta(hours=2),
        )

        async with AsyncSessionLocal() as db:
            reconciled = await reconcile_stale_pending(db)

        assert any(r["id"] == task_id for r in reconciled), "stale task should be reconciled"
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_reconcile_orphan_running_reclaims() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        task_id = await _create_task(
            f"test_audit_{marker}_orphan", "running",
            started_at=now - timedelta(seconds=audit.ORPHAN_RUNNING_TIMEOUT_SECONDS + 120),
        )

        async with AsyncSessionLocal() as db:
            reconciled = await reconcile_orphan_running(db)

        assert any(r["id"] == task_id for r in reconciled), "orphan should be reconciled"
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_audit_includes_handler_breakdown() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        await _create_task(f"test_audit_{marker}_h1", "failed", module="test",
                           error_message="err1",
                           completed_at=datetime.now(timezone.utc) - timedelta(minutes=10))
        await _create_task(f"test_audit_{marker}_h1", "completed", module="test")

        async with AsyncSessionLocal() as db:
            audit_result = await audit.audit_task_queue(db)

        breakdown = audit_result["handler_breakdown"]
        found = False
        for htype, states in breakdown.items():
            if marker in htype:
                found = True
                break
        assert found, "handler breakdown should include test tasks"
        assert len(audit_result["top_error_signatures"]) >= 0
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_audit_reports_stalest_pending() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        await _create_task(
            f"test_audit_{marker}_oldest", "pending",
            created_at=now - timedelta(hours=3),
        )

        async with AsyncSessionLocal() as db:
            audit_result = await audit.audit_task_queue(db)

        stalest = audit_result["stalest_pending"]
        assert stalest is not None, "should report stalest pending"
        assert stalest["age_seconds"] > 0
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_audit_metadata_includes_thresholds() -> None:
    async with AsyncSessionLocal() as db:
        audit_result = await audit.audit_task_queue(db)

    meta = audit_result["metadata"]
    assert meta["recent_failure_window_hours"] == audit.RECENT_FAILURE_WINDOW_HOURS
    assert meta["debt_cutoff_hours"] == audit.HISTORICAL_DEBT_CUTOFF_HOURS
    assert meta["stale_pending_threshold_seconds"] == audit.STALE_PENDING_THRESHOLD_SECONDS
    assert meta["orphan_timeout_seconds"] == audit.ORPHAN_RUNNING_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_debt_governance_dry_run_classifies_kb_source_without_mutating() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        missing_file_doc_id = await _create_file_and_document(marker, missing_file_row=True)
        obsolete_doc_id = await _create_file_and_document(
            f"{marker}_deleted",
            document_deleted=True,
            missing_file_row=True,
        )
        retry_task_id = await _create_task(
            "kb_pipeline",
            "failed",
            module="knowledge",
            completed_at=now - timedelta(hours=2),
            error_message="File not found",
            parameters={"marker": marker, "document_id": missing_file_doc_id, "user_id": 1},
        )
        obsolete_task_id = await _create_task(
            "kb_pipeline",
            "failed",
            module="knowledge",
            completed_at=now - timedelta(hours=2),
            error_message="File not found",
            parameters={"marker": marker, "document_id": obsolete_doc_id, "user_id": 1},
        )

        async with AsyncSessionLocal() as db:
            plan = await govern_task_queue_debt(
                db,
                dry_run=True,
                limit=2000,
                sample_limit=10,
                task_ids=[retry_task_id, obsolete_task_id],
            )

        assert plan["dry_run"] is True
        assert plan["processed"] == 0
        assert plan["summary_by_category"]["kb_source_unavailable_retry_once"] >= 1
        assert plan["summary_by_category"]["kb_document_obsolete"] >= 1

        async with AsyncSessionLocal() as db:
            statuses = await db.execute(
                text(
                    """
                    SELECT id, status
                    FROM framework_system_task_queues
                    WHERE id IN (:retry_task_id, :obsolete_task_id)
                    ORDER BY id
                    """
                ),
                {"retry_task_id": retry_task_id, "obsolete_task_id": obsolete_task_id},
            )
            assert {row[0]: row[1] for row in statuses.all()} == {
                retry_task_id: "failed",
                obsolete_task_id: "failed",
            }
    finally:
        await _cleanup(marker)
        await _cleanup(f"{marker}_deleted")


@pytest.mark.asyncio
async def test_debt_governance_apply_retries_and_archives_without_deleting_rows() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        missing_file_doc_id = await _create_file_and_document(marker, file_deleted=True)
        retry_task_id = await _create_task(
            "kb_pipeline",
            "failed",
            module="knowledge",
            completed_at=now - timedelta(hours=2),
            error_message="File not found",
            parameters={"marker": marker, "document_id": missing_file_doc_id, "user_id": 1},
        )
        test_task_id = await _create_task(
            "__emergency08_missing_handler__",
            "failed",
            module="test",
            completed_at=now - timedelta(hours=2),
            error_message="No handler registered for task_type '__emergency08_missing_handler__'",
            parameters={"marker": marker},
        )

        async with AsyncSessionLocal() as db:
            plan = await govern_task_queue_debt(
                db,
                dry_run=False,
                limit=2000,
                sample_limit=10,
                task_ids=[retry_task_id, test_task_id],
            )

        assert plan["processed"] >= 2
        assert plan["summary_by_category"]["kb_source_unavailable_retry_once"] >= 1
        assert plan["summary_by_category"]["test_missing_handler_archive"] >= 1

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                text(
                    """
                    SELECT id, status, error_message, result
                    FROM framework_system_task_queues
                    WHERE id IN (:retry_task_id, :test_task_id)
                    """
                ),
                {"retry_task_id": retry_task_id, "test_task_id": test_task_id},
            )
            by_id = {row[0]: row for row in rows.all()}
            assert by_id[retry_task_id][1] == "pending"
            assert by_id[retry_task_id][2] is None
            assert by_id[test_task_id][1] == "completed"
            assert by_id[test_task_id][2] is None
            assert json.loads(by_id[test_task_id][3])["status"] == "archived_test_debt"
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_debt_governance_dedupes_legacy_profile_init_db_failures() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        first_id = await _create_task(
            "profile_evolve",
            "failed",
            module="agent",
            completed_at=now - timedelta(hours=2),
            error_message="No module named 'init_db'",
            parameters={"marker": marker, "owner_id": 4, "conversation_id": 77},
        )
        second_id = await _create_task(
            "profile_evolve",
            "failed",
            module="agent",
            completed_at=now - timedelta(hours=2),
            error_message="No module named 'init_db'",
            parameters={"marker": marker, "owner_id": 4, "conversation_id": 77},
        )

        async with AsyncSessionLocal() as db:
            plan = await govern_task_queue_debt(
                db,
                dry_run=False,
                limit=2000,
                sample_limit=10,
                task_ids=[first_id, second_id],
            )

        assert plan["summary_by_category"]["profile_evolve_legacy_init_db_retry_once"] >= 1
        assert plan["summary_by_category"]["profile_evolve_legacy_init_db_duplicate"] >= 1

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                text(
                    """
                    SELECT id, status, result
                    FROM framework_system_task_queues
                    WHERE id IN (:first_id, :second_id)
                    ORDER BY id
                    """
                ),
                {"first_id": first_id, "second_id": second_id},
            )
            statuses = {row[0]: (row[1], row[2]) for row in rows.all()}
            assert statuses[first_id][0] == "pending"
            assert statuses[second_id][0] == "completed"
            assert json.loads(statuses[second_id][1])["status"] == "obsolete"
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_debt_governance_profile_json_parse_failure_requires_manual_review() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        task_id = await _create_task(
            "profile_evolve",
            "failed",
            module="agent",
            completed_at=now - timedelta(hours=2),
            error_message="Failed to parse profile JSON",
            parameters={"marker": marker, "owner_id": 4, "conversation_id": 78},
        )

        async with AsyncSessionLocal() as db:
            plan = await govern_task_queue_debt(
                db,
                dry_run=False,
                limit=2000,
                sample_limit=10,
                task_ids=[task_id],
            )

        assert plan["summary_by_category"]["profile_evolve_json_parse_manual_review"] >= 1
        assert plan["summary_by_action"]["manual_review"] >= 1
        assert plan["processed"] == 0

        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text(
                    """
                    SELECT status, error_message, result
                    FROM framework_system_task_queues
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            )
            status, error_message, result = row.one()
            assert status == "failed"
            assert error_message == "Failed to parse profile JSON"
            assert result is None
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_completed_semantic_failure_is_audit_and_governance_readonly_debt() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            baseline = await audit.audit_task_queue(db)
        baseline_count = baseline["classification"]["completed_semantic_failure_count"]

        task_result = {
            "status": "failed",
            "error": "unparseable_llm_profile_json",
            "retryable": True,
        }
        task_id = await _create_task(
            "profile_evolve",
            "completed",
            module="agent",
            completed_at=now - timedelta(hours=2),
            parameters={"marker": marker, "owner_id": 4, "conversation_id": 79},
            result=task_result,
        )

        async with AsyncSessionLocal() as db:
            audit_result = await audit.audit_task_queue(db)

        semantic = audit_result["completed_semantic_failures"]
        assert audit_result["classification"]["completed_semantic_failure_count"] >= baseline_count + 1
        assert semantic["mutates_rows"] is False
        assert any(sample["id"] == task_id for sample in semantic["samples"])

        async with AsyncSessionLocal() as db:
            plan = await govern_task_queue_debt(
                db,
                dry_run=False,
                limit=2000,
                sample_limit=10,
                task_ids=[task_id],
            )

        assert plan["readonly_review"]["mutates_completed_rows"] is False
        assert plan["readonly_review"]["completed_semantic_failure_count"] >= 1
        assert plan["summary_by_category"]["completed_semantic_failure_manual_review"] >= 1
        assert plan["processed"] == 0

        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text(
                    """
                    SELECT status, result
                    FROM framework_system_task_queues
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            )
            status, stored_result = row.one()
            assert status == "completed"
            assert json.loads(stored_result) == task_result
    finally:
        await _cleanup(marker)
