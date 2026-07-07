"""Enterprise source-folder import helpers for the knowledge module."""
from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
import tempfile
from pathlib import Path

from app.core.exceptions import ValidationError
from app.models.file import File, Folder
from app.services.file_upload_service import upload_file_from_path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .document_service import SUPPORTED_EXTENSIONS, register_document

DEFAULT_IMPORT_EXTENSIONS = {
    "pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls",
    "jpg", "jpeg", "png", "webp", "bmp", "tiff", "txt", "md",
}
VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "wmv", "flv", "m4v"}


def _normalize_extensions(values: list[str] | None) -> set[str]:
    if not values:
        return set(DEFAULT_IMPORT_EXTENSIONS)
    normalized = set()
    for value in values:
        ext = str(value).lower().strip().lstrip(".")
        if not ext:
            continue
        normalized.add("tiff" if ext == "tif" else ext)
    return {ext for ext in normalized if ext in SUPPORTED_EXTENSIONS and ext not in VIDEO_EXTENSIONS}


def _file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_import_path(target_root_name: str, relative_path: Path) -> str:
    parent = relative_path.parent
    if str(parent) == ".":
        return target_root_name
    return str(Path(target_root_name) / parent)


def _iter_source_files(source_root: Path, extensions: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower().lstrip(".")
        if ext == "tif":
            ext = "tiff"
        if ext not in extensions:
            continue
        files.append(path)
    return sorted(files, key=lambda item: str(item.relative_to(source_root)))


async def _find_folder_id(db: AsyncSession, owner_id: int, relative_path: str) -> int | None:
    current_parent: int | None = None
    for part in [part for part in relative_path.split("/") if part]:
        condition = Folder.parent_id.is_(None) if current_parent is None else Folder.parent_id == current_parent
        result = await db.execute(
            select(Folder).where(
                Folder.name == part,
                condition,
                Folder.owner_id == owner_id,
                Folder.deleted.is_(False),
            )
        )
        folder = result.scalar_one_or_none()
        if folder is None:
            return None
        current_parent = int(folder.id)
    return current_parent


async def _find_existing_target_file(
    db: AsyncSession,
    *,
    owner_id: int,
    target_relative_path: str,
    filename: str,
) -> File | None:
    folder_id = await _find_folder_id(db, owner_id, target_relative_path)
    if folder_id is None:
        return None
    name_part, ext_part = os.path.splitext(filename)
    result = await db.execute(
        select(File).where(
            File.name == name_part,
            File.extension == ext_part.lstrip(".").lower(),
            File.folder_id == folder_id,
            File.owner_id == owner_id,
            File.deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def import_enterprise_source_batch(
    db: AsyncSession,
    *,
    owner_id: int,
    source_root: str,
    target_root_name: str = "企业微盘导入",
    limit: int = 20,
    dry_run: bool = True,
    extensions: list[str] | None = None,
    skip_existing_md5: bool = True,
) -> dict:
    """Dry-run or import a bounded batch from a local enterprise source folder."""
    root = Path(source_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValidationError("source_root must be an existing directory")
    clean_target_root = (target_root_name or "企业微盘导入").strip().strip("/") or "企业微盘导入"
    bounded_limit = max(1, min(int(limit or 20), 200))
    allowed_extensions = _normalize_extensions(extensions)

    existing_md5: set[str] = set()
    if skip_existing_md5:
        existing_md5 = set((await db.execute(
            select(File.md5_hash).where(
                File.owner_id == owner_id,
                File.deleted.is_(False),
                File.md5_hash.is_not(None),
            )
        )).scalars().all())

    imported = []
    selected = []
    skipped = []
    for source_path in _iter_source_files(root, allowed_extensions):
        relative_path = source_path.relative_to(root)
        try:
            md5_hash = _file_md5(source_path)
        except OSError as exc:
            skipped.append({"path": str(relative_path), "reason": f"read_failed:{exc}"})
            continue
        duplicate_content = bool(skip_existing_md5 and md5_hash in existing_md5)
        item = {
            "path": str(relative_path),
            "size": source_path.stat().st_size,
            "md5_hash": md5_hash,
            "extension": source_path.suffix.lower().lstrip("."),
            "target_relative_path": _relative_import_path(clean_target_root, relative_path),
            "content_action": "reuse_existing_content" if duplicate_content else "store_new_content",
        }
        existing_target = await _find_existing_target_file(
            db,
            owner_id=owner_id,
            target_relative_path=item["target_relative_path"],
            filename=source_path.name,
        )
        if existing_target is not None:
            reason = (
                "target_file_already_imported"
                if existing_target.md5_hash == md5_hash
                else "target_name_conflict"
            )
            skipped.append({"path": str(relative_path), "reason": reason})
            continue
        selected.append(item)

        if dry_run:
            if len(selected) >= bounded_limit:
                break
            continue

        mime_type = mimetypes.guess_type(str(source_path))[0] or "application/octet-stream"
        with tempfile.TemporaryDirectory(prefix="kb-enterprise-import-") as temp_dir:
            temp_path = Path(temp_dir) / source_path.name
            shutil.copy2(source_path, temp_path)
            file_info = await upload_file_from_path(
                db,
                temp_path,
                source_path.name,
                owner_id,
                relative_path=item["target_relative_path"],
                md5_hex=md5_hash,
                mime_type=mime_type,
            )
            doc_info = await register_document(db, int(file_info["id"]), owner_id)
        imported.append({
            **item,
            "file_id": int(file_info["id"]),
            "document_id": int(doc_info["document_id"]),
            "task_id": doc_info.get("task_id"),
            "enqueued": bool(doc_info.get("enqueued")),
            "reason": doc_info.get("reason"),
            "deduplicated": bool(file_info.get("deduplicated")),
            "duplicate_reused": bool(doc_info.get("duplicate_reused")),
        })
        existing_md5.add(md5_hash)
        if len(selected) >= bounded_limit:
            break

    return {
        "dry_run": dry_run,
        "source_root": str(root),
        "target_root_name": clean_target_root,
        "limit": bounded_limit,
        "extensions": sorted(allowed_extensions),
        "selected": len(selected),
        "imported": len(imported),
        "skipped": len(skipped),
        "items": selected if dry_run else imported,
        "skipped_sample": skipped[:50],
    }
