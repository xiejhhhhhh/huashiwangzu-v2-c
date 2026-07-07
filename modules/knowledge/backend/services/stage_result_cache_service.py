"""Local outbox cache for knowledge stage results before DB commit."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

CACHE_SCHEMA_VERSION = "knowledge_stage_result_cache_v1"
ENV_CACHE_DIR = "KNOWLEDGE_STAGE_RESULT_CACHE_DIR"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def get_stage_result_cache_dir() -> Path:
    configured = os.getenv(ENV_CACHE_DIR)
    if configured:
        return Path(configured).expanduser().resolve()
    return _repo_root() / "backend" / "data" / "runtime" / "knowledge_stage_result_cache"


def _safe_part(value: Any) -> str:
    text = str(value or "unknown")
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)[:80] or "unknown"


def write_stage_result_cache(
    *,
    document_id: int,
    file_id: int | None,
    owner_id: int,
    stage: str,
    status: str,
    result: dict[str, Any],
    task_id: int | None = None,
    pipeline_run_id: int | None = None,
    reason: str = "",
    started_at: datetime | None = None,
    duration_ms: int | None = None,
    cache_dir: Path | None = None,
) -> Path:
    """Atomically write a stage result cache file.

    The caller should delete the returned path only after the DB commit that
    persists the same result has succeeded.
    """
    root = cache_dir or get_stage_result_cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "created_at": now.isoformat(),
        "document_id": int(document_id),
        "file_id": int(file_id) if file_id is not None else None,
        "owner_id": int(owner_id),
        "stage": stage,
        "status": status,
        "reason": reason,
        "task_id": int(task_id) if task_id is not None else None,
        "pipeline_run_id": int(pipeline_run_id) if pipeline_run_id is not None else None,
        "started_at": started_at.isoformat() if started_at else None,
        "duration_ms": duration_ms,
        "result": result,
    }
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    filename = (
        f"{stamp}_doc-{int(document_id)}_run-{_safe_part(pipeline_run_id)}_"
        f"task-{_safe_part(task_id)}_{_safe_part(stage)}_{uuid4().hex}.json"
    )
    final_path = root / filename
    tmp_path = final_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp_path.replace(final_path)
    return final_path


def delete_stage_result_cache(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
