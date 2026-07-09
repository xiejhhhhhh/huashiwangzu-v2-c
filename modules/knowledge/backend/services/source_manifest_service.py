"""Durable external source inventory for knowledge imports."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from app.core.exceptions import ValidationError
from app.models.system import SystemTaskQueue
from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbSourceFileManifest
from .enterprise_import_service import (
    ENTERPRISE_IMPORT_FILE_TASK,
    is_ignored_source_path,
    _normalize_extensions,
)


def _fingerprint(size: int, mtime_ns: int) -> str:
    return f"{int(size)}:{int(mtime_ns)}"


def _normalize_ext(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return "tiff" if ext == "tif" else ext


def _iter_manifest_files(source_root: Path, extensions: set[str]):
    for path in source_root.rglob("*"):
        if is_ignored_source_path(path):
            continue
        if not path.is_file():
            continue
        ext = _normalize_ext(path)
        if ext in extensions:
            yield path, ext


async def scan_source_manifest(
    db: AsyncSession,
    *,
    owner_id: int,
    source_root: str,
    target_root_name: str = "企业微盘导入",
    extensions: list[str] | None = None,
    limit: int = 10000,
    mark_missing: bool = False,
) -> dict[str, Any]:
    """Scan an external source root into a durable manifest without importing files."""
    root = Path(source_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValidationError("source_root must be an existing directory")
    allowed_extensions = _normalize_extensions(extensions)
    bounded_limit = max(1, min(int(limit or 10000), 200000))
    scan_id = uuid.uuid4().hex
    clean_target_root = (target_root_name or "企业微盘导入").strip().strip("/") or "企业微盘导入"

    scanned = 0
    inserted_or_updated = 0
    changed = 0
    samples: list[dict[str, Any]] = []

    for source_path, ext in _iter_manifest_files(root, allowed_extensions):
        if scanned >= bounded_limit:
            break
        scanned += 1
        stat = source_path.stat()
        relative_path = str(source_path.relative_to(root))
        size = int(stat.st_size)
        mtime_ns = int(stat.st_mtime_ns)
        fingerprint = _fingerprint(size, mtime_ns)
        values = {
            "owner_id": int(owner_id),
            "source_root": str(root),
            "relative_path": relative_path,
            "source_path": str(source_path),
            "target_root_name": clean_target_root,
            "extension": ext,
            "size": size,
            "mtime_ns": mtime_ns,
            "fingerprint": fingerprint,
            "scan_id": scan_id,
            "import_status": "discovered",
            "error_message": None,
        }
        stmt = insert(KbSourceFileManifest).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_kb_source_file_manifest_owner_root_path",
            set_={
                "source_path": stmt.excluded.source_path,
                "target_root_name": stmt.excluded.target_root_name,
                "extension": stmt.excluded.extension,
                "size": stmt.excluded.size,
                "mtime_ns": stmt.excluded.mtime_ns,
                "fingerprint": stmt.excluded.fingerprint,
                "scan_id": stmt.excluded.scan_id,
                "import_status": case(
                    (
                        KbSourceFileManifest.fingerprint != stmt.excluded.fingerprint,
                        "changed",
                    ),
                    else_=KbSourceFileManifest.import_status,
                ),
                "error_message": None,
            },
        ).returning(KbSourceFileManifest.id, KbSourceFileManifest.import_status)
        row = (await db.execute(stmt)).mappings().one()
        inserted_or_updated += 1
        if row["import_status"] == "changed":
            changed += 1
        if len(samples) < 20:
            samples.append({
                "manifest_id": int(row["id"]),
                "relative_path": relative_path,
                "extension": ext,
                "size": size,
                "status": row["import_status"],
            })
        if scanned % 500 == 0:
            await db.commit()

    missing_marked = 0
    if mark_missing and scanned < bounded_limit:
        result = await db.execute(
            update(KbSourceFileManifest)
            .where(
                KbSourceFileManifest.owner_id == int(owner_id),
                KbSourceFileManifest.source_root == str(root),
                KbSourceFileManifest.scan_id != scan_id,
                KbSourceFileManifest.import_status != "missing",
            )
            .values(import_status="missing", error_message="not_seen_in_latest_scan")
        )
        missing_marked = int(result.rowcount or 0)
    await db.commit()

    return {
        "source_root": str(root),
        "target_root_name": clean_target_root,
        "extensions": sorted(allowed_extensions),
        "scan_id": scan_id,
        "limit": bounded_limit,
        "scanned": scanned,
        "upserted": inserted_or_updated,
        "changed": changed,
        "missing_marked": missing_marked,
        "truncated": scanned >= bounded_limit,
        "samples": samples,
    }


async def source_manifest_summary(
    db: AsyncSession,
    *,
    owner_id: int,
    source_root: str | None = None,
) -> dict[str, Any]:
    stmt = select(
        KbSourceFileManifest.source_root,
        KbSourceFileManifest.extension,
        KbSourceFileManifest.import_status,
        func.count(KbSourceFileManifest.id).label("count"),
    ).where(KbSourceFileManifest.owner_id == int(owner_id))
    if source_root:
        stmt = stmt.where(KbSourceFileManifest.source_root == str(Path(source_root).expanduser().resolve()))
    stmt = stmt.group_by(
        KbSourceFileManifest.source_root,
        KbSourceFileManifest.extension,
        KbSourceFileManifest.import_status,
    ).order_by(KbSourceFileManifest.source_root, KbSourceFileManifest.import_status, KbSourceFileManifest.extension)
    rows = [dict(row) for row in (await db.execute(stmt)).mappings().all()]
    totals: dict[str, int] = {}
    for row in rows:
        status = str(row["import_status"])
        totals[status] = totals.get(status, 0) + int(row["count"] or 0)
    return {"rows": rows, "totals": totals}


async def enqueue_source_manifest_import(
    db: AsyncSession,
    *,
    owner_id: int,
    source_root: str,
    target_root_name: str = "企业微盘导入",
    extensions: list[str] | None = None,
    limit: int = 1000,
    priority: int = 8,
    skip_existing_md5: bool = True,
) -> dict[str, Any]:
    root = Path(source_root).expanduser().resolve()
    allowed_extensions = _normalize_extensions(extensions)
    bounded_limit = max(1, min(int(limit or 1000), 50000))
    clean_target_root = (target_root_name or "企业微盘导入").strip().strip("/") or "企业微盘导入"

    result = await db.execute(
        select(KbSourceFileManifest)
        .where(
            KbSourceFileManifest.owner_id == int(owner_id),
            KbSourceFileManifest.source_root == str(root),
            KbSourceFileManifest.extension.in_(allowed_extensions),
            KbSourceFileManifest.import_status.in_(("discovered", "changed", "error")),
        )
        .order_by(KbSourceFileManifest.id.asc())
        .limit(bounded_limit)
    )
    rows = result.scalars().all()
    enqueued = 0
    skipped_missing = 0
    skipped_ignored = 0
    samples: list[dict[str, Any]] = []
    for item in rows:
        source_path = Path(item.source_path)
        if not source_path.exists() or not source_path.is_file():
            item.import_status = "missing"
            item.error_message = "source_file_missing"
            skipped_missing += 1
            continue
        if is_ignored_source_path(source_path):
            item.import_status = "skipped"
            item.error_message = "ignored_source_path"
            skipped_ignored += 1
            continue
        params = {
            "owner_id": int(owner_id),
            "source_root": str(root),
            "source_path": str(source_path),
            "relative_path": item.relative_path,
            "target_root_name": clean_target_root,
            "skip_existing_md5": bool(skip_existing_md5),
            "source_manifest_id": int(item.id),
        }
        task = SystemTaskQueue(
            task_type=ENTERPRISE_IMPORT_FILE_TASK,
            module="knowledge",
            parameters=json.dumps(params, ensure_ascii=False),
            priority=int(priority),
            status="pending",
            creator_id=int(owner_id),
        )
        db.add(task)
        await db.flush()
        item.import_status = "queued"
        item.import_task_id = int(task.id)
        item.target_root_name = clean_target_root
        item.error_message = None
        enqueued += 1
        if len(samples) < 20:
            samples.append({
                "manifest_id": int(item.id),
                "task_id": int(task.id),
                "relative_path": item.relative_path,
                "extension": item.extension,
            })
        if enqueued % 500 == 0:
            await db.commit()
    await db.commit()
    return {
        "source_root": str(root),
        "target_root_name": clean_target_root,
        "extensions": sorted(allowed_extensions),
        "limit": bounded_limit,
        "matched": len(rows),
        "enqueued": enqueued,
        "skipped_missing": skipped_missing,
        "skipped_ignored": skipped_ignored,
        "samples": samples,
    }
