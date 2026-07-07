"""Dry-run first governance for historical task queue debt."""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.system import SystemTaskQueue

logger = logging.getLogger("v2.task_debt_governance")

DEBT_GOVERNANCE_MAX_LIMIT = 5000
DEFAULT_DEBT_GOVERNANCE_LIMIT = 1000
KB_DELETED_SOURCE_OBSOLETE_CATEGORY = "kb_deleted_source_obsolete"
KNOWLEDGE_PIPELINE_TASK_TYPES = {"kb_pipeline_stage", "kb_pipeline"}

_DOCUMENT_NOT_FOUND_RE = re.compile(r"Document\s+(\d+)\s+not found")


def _parse_task_parameters(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_task_result(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _task_result_semantic_failure_reason(result: dict | None) -> str | None:
    if not isinstance(result, dict):
        return None
    if result.get("success") is False:
        return str(result.get("error") or "Task result success=false")
    status = result.get("status")
    if isinstance(status, str) and status.lower() in {"failed", "error"}:
        return str(result.get("error") or f"Task result status={status}")
    if result.get("error") not in (None, "") and result.get("success") is not True:
        return str(result.get("error"))
    return None


def _task_sample(task: SystemTaskQueue, *, params: dict | None = None) -> dict:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "module": task.module,
        "error_message": task.error_message,
        "parameters": params if params is not None else _parse_task_parameters(task.parameters),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "retry_count": task.retry_count,
    }


def _completed_semantic_failure_sample(task: SystemTaskQueue, reason: str) -> dict:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "module": task.module,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "reason": reason,
        "parameters": _parse_task_parameters(task.parameters),
    }


def _empty_action_summary() -> dict:
    return {
        "retry_once": 0,
        "mark_obsolete": 0,
        "archive_test_debt": 0,
        "manual_review": 0,
    }


def _append_readonly_review_group(
    plan: dict,
    *,
    category: str,
    action: str,
    reason: str,
    count: int,
    samples: list[dict],
) -> None:
    if count <= 0:
        return
    plan["summary_by_category"][category] = plan["summary_by_category"].get(category, 0) + count
    plan["summary_by_action"][action] = plan["summary_by_action"].get(action, 0) + count
    plan["groups"][category] = {
        "action": action,
        "count": count,
        "reason": reason,
        "samples": samples,
        "readonly": True,
    }


def _append_plan(plan: dict, classification: dict, *, sample_limit: int) -> None:
    category = classification["category"]
    action = classification["action"]
    plan["summary_by_category"][category] = plan["summary_by_category"].get(category, 0) + 1
    plan["summary_by_action"][action] = plan["summary_by_action"].get(action, 0) + 1
    bucket = plan["groups"].setdefault(category, {
        "action": action,
        "count": 0,
        "reason": classification["reason"],
        "samples": [],
    })
    bucket["count"] += 1
    if len(bucket["samples"]) < sample_limit:
        bucket["samples"].append(classification["sample"])


async def _append_completed_semantic_failure_reviews(
    db: AsyncSession,
    plan: dict,
    *,
    sample_limit: int,
    task_ids: list[int] | None,
    limit: int,
) -> None:
    filters = [
        SystemTaskQueue.status == "completed",
        SystemTaskQueue.result.is_not(None),
        SystemTaskQueue.result != "",
    ]
    if task_ids:
        filters.append(SystemTaskQueue.id.in_(task_ids))
    stmt = (
        select(SystemTaskQueue)
        .where(and_(*filters))
        .order_by(SystemTaskQueue.completed_at.desc().nulls_last(), SystemTaskQueue.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    count = 0
    samples = []
    for task in result.scalars().all():
        reason = _task_result_semantic_failure_reason(_parse_task_result(task.result))
        if reason is None:
            continue
        count += 1
        if len(samples) < sample_limit:
            samples.append(_completed_semantic_failure_sample(task, reason))

    plan["readonly_review"]["completed_semantic_failure_count"] = count
    plan["readonly_review"]["completed_semantic_failure_samples"] = samples
    _append_readonly_review_group(
        plan,
        category="completed_semantic_failure_manual_review",
        action="manual_review",
        reason=(
            "Task is marked completed, but its result JSON still reports a semantic failure "
            "(error/status=failed/success=false). Keep the row intact and review manually."
        ),
        count=count,
        samples=samples,
    )


def _document_id_from_task(task: SystemTaskQueue, params: dict) -> int | None:
    raw = params.get("document_id")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    match = _DOCUMENT_NOT_FOUND_RE.search(task.error_message or "")
    if match:
        return int(match.group(1))
    return None


async def _load_kb_document_state(db: AsyncSession, document_id: int | None) -> dict:
    if document_id is None:
        return {"doc_state": "unknown", "file_state": "unknown"}
    row = await db.execute(
        text(
            """
            SELECT
                d.id AS document_id,
                d.deleted AS doc_deleted,
                d.file_id AS document_file_id,
                f.id AS file_id,
                f.deleted AS file_deleted,
                f.storage_path AS storage_path
            FROM kb_documents d
            LEFT JOIN framework_file_items f ON f.id = d.file_id
            WHERE d.id = :document_id
            """
        ),
        {"document_id": document_id},
    )
    record = row.mappings().first()
    if not record:
        return {
            "document_id": document_id,
            "doc_state": "doc_missing",
            "file_state": "unknown",
        }

    doc_state = "doc_deleted" if record["doc_deleted"] else "doc_live"
    if record["file_id"] is None:
        file_state = "no_file_row"
    elif record["file_deleted"]:
        file_state = "file_row_deleted"
    else:
        file_state = "file_row_live"

    storage_path = record["storage_path"]
    physical_exists = None
    if file_state == "file_row_live" and storage_path:
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / storage_path).resolve()
        try:
            physical_exists = str(full_path).startswith(str(upload_root)) and full_path.exists()
        except OSError:
            physical_exists = False

    return {
        "document_id": document_id,
        "doc_state": doc_state,
        "file_state": file_state,
        "file_id": record["file_id"],
        "storage_path": storage_path,
        "physical_exists": physical_exists,
    }


def _is_kb_deleted_source_obsolete_state(doc_state: dict) -> bool:
    return doc_state.get("doc_state") in {"doc_deleted", "doc_missing"} and doc_state.get("file_state") in {
        "no_file_row",
        "file_row_deleted",
        "unknown",
    }


def _kb_deleted_source_obsolete_classification(task: SystemTaskQueue, sample: dict) -> dict:
    return {
        "task": task,
        "action": "mark_obsolete",
        "category": KB_DELETED_SOURCE_OBSOLETE_CATEGORY,
        "reason": (
            "Knowledge pipeline task references a deleted/missing knowledge document whose source file row "
            "is unavailable; the failed task is obsolete and should not be retried."
        ),
        "sample": sample,
    }


async def _classify_kb_pipeline_debt(db: AsyncSession, task: SystemTaskQueue, params: dict) -> dict:
    error = task.error_message or ""
    document_id = _document_id_from_task(task, params)
    doc_state = await _load_kb_document_state(db, document_id)
    sample = _task_sample(task, params=params)
    sample.update(doc_state)

    if _is_kb_deleted_source_obsolete_state(doc_state):
        return _kb_deleted_source_obsolete_classification(task, sample)

    if error == "File not found":
        if doc_state["doc_state"] == "doc_live" and doc_state["file_state"] in {"no_file_row", "file_row_deleted"}:
            return {
                "task": task,
                "action": "retry_once",
                "category": "kb_source_unavailable_retry_once",
                "reason": (
                    "Knowledge document is still live but the source file row is missing/deleted; "
                    "retry once so the current handler records source_file_missing/source_file_deleted and skips cleanly."
                ),
                "sample": sample,
            }
        if doc_state["doc_state"] in {"doc_deleted", "doc_missing"}:
            return _kb_deleted_source_obsolete_classification(task, sample)
        if doc_state["file_state"] == "file_row_live":
            return {
                "task": task,
                "action": "manual_review",
                "category": "kb_live_file_manual_review",
                "reason": "File row is live; inspect parser/source path before retrying.",
                "sample": sample,
            }

    if _DOCUMENT_NOT_FOUND_RE.search(error):
        return _kb_deleted_source_obsolete_classification(task, sample)

    if "Parser returned no content blocks" in error:
        return {
            "task": task,
            "action": "manual_review",
            "category": "kb_parser_empty_manual_review",
            "reason": "Parser produced no content; sample documents should be inspected before any bulk retry.",
            "sample": sample,
        }

    if "Document is already parsing" in error or "greenlet_spawn has not been called" in error:
        return {
            "task": task,
            "action": "retry_once",
            "category": "kb_transient_retry_once",
            "reason": "Historical transient pipeline failure; retry once under the hardened handler.",
            "sample": sample,
        }

    return {
        "task": task,
        "action": "manual_review",
        "category": "kb_unknown_manual_review",
        "reason": "Knowledge pipeline failure is not in an allowlisted bulk-governance class.",
        "sample": sample,
    }


async def classify_failed_task_debt(db: AsyncSession, task: SystemTaskQueue) -> dict:
    """Classify one failed task using the same rules as governance dry-run/apply."""
    return await _classify_failed_task(db, task, set())


def _profile_dedupe_key(params: dict) -> tuple[str, str] | None:
    owner_id = params.get("owner_id")
    conversation_id = params.get("conversation_id")
    if owner_id is None or conversation_id is None:
        return None
    return str(owner_id), str(conversation_id)


def _classify_profile_evolve_debt(
    task: SystemTaskQueue,
    params: dict,
    profile_init_seen: set[tuple[str, str]],
) -> dict:
    error = task.error_message or ""
    sample = _task_sample(task, params=params)
    if error == "No module named 'init_db'":
        key = _profile_dedupe_key(params)
        sample["dedupe_key"] = list(key) if key else None
        if key is None:
            return {
                "task": task,
                "action": "manual_review",
                "category": "profile_evolve_legacy_init_db_missing_params",
                "reason": "Legacy init_db failure lacks owner/conversation parameters, so it cannot be safely deduped.",
                "sample": sample,
            }
        if key in profile_init_seen:
            return {
                "task": task,
                "action": "mark_obsolete",
                "category": "profile_evolve_legacy_init_db_duplicate",
                "reason": "Duplicate legacy profile evolve task for the same owner/conversation; keep one retry and obsolete the rest.",
                "sample": sample,
            }
        profile_init_seen.add(key)
        return {
            "task": task,
            "action": "retry_once",
            "category": "profile_evolve_legacy_init_db_retry_once",
            "reason": "Legacy worker import path failed; current handler no longer uses init_db, so one deduped retry is safe.",
            "sample": sample,
        }

    if error == "Failed to parse profile JSON":
        return {
            "task": task,
            "action": "manual_review",
            "category": "profile_evolve_json_parse_manual_review",
            "reason": (
                "Current profile evolve handler returns status=failed with "
                "error=unparseable_llm_profile_json and retryable=true for unparseable LLM JSON; "
                "bulk retry can call the model again and create new failed noise."
            ),
            "sample": sample,
        }

    if error in {"No messages found", "Orphan task exceeded max retries on startup recovery"}:
        return {
            "task": task,
            "action": "mark_obsolete",
            "category": "profile_evolve_obsolete",
            "reason": "Historical profile task has no useful work left or was an orphan recovery artifact.",
            "sample": sample,
        }

    return {
        "task": task,
        "action": "manual_review",
        "category": "profile_evolve_unknown_manual_review",
        "reason": "Profile evolve failure is not in an allowlisted bulk-governance class.",
        "sample": sample,
    }


def _classify_test_debt(task: SystemTaskQueue, params: dict) -> dict | None:
    if task.task_type == "__emergency08_missing_handler__":
        return {
            "task": task,
            "action": "archive_test_debt",
            "category": "test_missing_handler_archive",
            "reason": "Known emergency audit test task with no production handler.",
            "sample": _task_sample(task, params=params),
        }
    if str(params.get("conversation_id")) == "999999":
        return {
            "task": task,
            "action": "archive_test_debt",
            "category": "test_conversation_archive",
            "reason": "Known synthetic conversation_id=999999 test debt.",
            "sample": _task_sample(task, params=params),
        }
    return None


async def _classify_failed_task(
    db: AsyncSession,
    task: SystemTaskQueue,
    profile_init_seen: set[tuple[str, str]],
) -> dict:
    params = _parse_task_parameters(task.parameters)
    test_classification = _classify_test_debt(task, params)
    if test_classification:
        return test_classification
    if task.task_type in KNOWLEDGE_PIPELINE_TASK_TYPES:
        return await _classify_kb_pipeline_debt(db, task, params)
    if task.task_type == "profile_evolve":
        return _classify_profile_evolve_debt(task, params, profile_init_seen)
    return {
        "task": task,
        "action": "manual_review",
        "category": "unknown_failed_task_manual_review",
        "reason": "No governance rule exists for this failed task type.",
        "sample": _task_sample(task, params=params),
    }


def _result_payload(task: SystemTaskQueue, classification: dict, status: str) -> str:
    return json.dumps({
        "status": status,
        "governed_by": "task_queue_debt_governance",
        "category": classification["category"],
        "reason": classification["reason"],
        "previous_error": task.error_message,
        "previous_parameters": _parse_task_parameters(task.parameters),
        "governed_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False)


async def govern_task_queue_debt(
    db: AsyncSession,
    *,
    dry_run: bool = True,
    limit: int = DEFAULT_DEBT_GOVERNANCE_LIMIT,
    sample_limit: int = 5,
    task_ids: list[int] | None = None,
    confirm_all_failed: bool = False,
) -> dict:
    """Classify and optionally govern historical failed task debt.

    Dry-run is the default and performs no writes. Non-dry-run never deletes rows:
    it either requeues a strictly allowlisted retry or converts obsolete/test debt
    into a truthful completed result with provenance.
    """
    if not dry_run and not task_ids and not confirm_all_failed:
        raise ValueError("Non-dry-run governance requires task_ids or confirm_all_failed=true")

    bounded_limit = max(1, min(int(limit), DEBT_GOVERNANCE_MAX_LIMIT))
    bounded_sample_limit = max(0, min(int(sample_limit), 20))
    filters = [SystemTaskQueue.status == "failed"]
    if task_ids:
        filters.append(SystemTaskQueue.id.in_(task_ids))
    stmt = (
        select(SystemTaskQueue)
        .where(and_(*filters))
        .order_by(SystemTaskQueue.task_type, SystemTaskQueue.id)
        .limit(bounded_limit)
    )
    if not dry_run:
        stmt = stmt.with_for_update(skip_locked=True)
    result = await db.execute(stmt)
    failed_tasks = list(result.scalars().all())

    plan = {
        "dry_run": dry_run,
        "limit": bounded_limit,
        "task_ids": task_ids or None,
        "confirm_all_failed": confirm_all_failed,
        "scanned": len(failed_tasks),
        "processed": 0,
        "summary_by_action": _empty_action_summary(),
        "summary_by_category": {},
        "groups": {},
        "readonly_review": {
            "completed_semantic_failure_count": 0,
            "completed_semantic_failure_samples": [],
            "mutates_completed_rows": False,
        },
        "safety": {
            "deleted_rows": 0,
            "default_dry_run": True,
            "manual_review_is_noop": True,
        },
    }
    await _append_completed_semantic_failure_reviews(
        db,
        plan,
        sample_limit=bounded_sample_limit,
        task_ids=task_ids,
        limit=bounded_limit,
    )
    profile_init_seen: set[tuple[str, str]] = set()
    classifications = []
    for task in failed_tasks:
        classification = await _classify_failed_task(db, task, profile_init_seen)
        classifications.append(classification)
        _append_plan(plan, classification, sample_limit=bounded_sample_limit)

    if dry_run:
        return plan

    now = datetime.now(timezone.utc)
    for classification in classifications:
        task = classification["task"]
        action = classification["action"]
        if action == "retry_once":
            task.status = "pending"
            task.retry_count = 0
            task.error_message = None
            task.result = None
            task.started_at = None
            task.completed_at = None
            task.updated_at = now
            plan["processed"] += 1
        elif action in {"mark_obsolete", "archive_test_debt"}:
            task.status = "completed"
            task.retry_count = task.retry_count or 0
            task.result = _result_payload(
                task,
                classification,
                "archived_test_debt" if action == "archive_test_debt" else "obsolete",
            )
            task.error_message = None
            task.started_at = None
            task.completed_at = now
            task.updated_at = now
            plan["processed"] += 1
    if plan["processed"]:
        await db.commit()
        logger.info("Governed %d historical task debt rows", plan["processed"])
    return plan
