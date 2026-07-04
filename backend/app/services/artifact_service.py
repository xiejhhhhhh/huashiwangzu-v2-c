"""Artifact lifecycle service.

Unified interface for product lifecycle management:
- create / get / list / update / replace / delete / restore
- version management (create / list / restore)
- operation history tracking
- export / publish to desktop
- conflict strategy (fail / overwrite / auto_rename / create_version / replace_existing)
"""
import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFound, PermissionDenied, ValidationError
from app.models.artifact import Artifact, ArtifactOperation, ArtifactVersion
from app.models.file import File
from app.services.file_reader import get_file_content_bytes
from app.services.file_service import check_file_access
from app.services.file_upload_service import replace_file_content, upload_file

logger = logging.getLogger("v2.artifact_service")

CONFLICT_FAIL = "fail"
CONFLICT_OVERWRITE = "overwrite"
CONFLICT_AUTO_RENAME = "auto_rename"
CONFLICT_CREATE_VERSION = "create_version"
CONFLICT_REPLACE_EXISTING = "replace_existing"

DEFAULT_CONFLICT_POLICY = CONFLICT_CREATE_VERSION

KIND_MIME_MAP: dict[str, str] = {
    "document": "application/octet-stream",
    "spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "image": "image/png",
    "video": "video/mp4",
    "audio": "audio/mpeg",
    "binary": "application/octet-stream",
    "draft": "text/plain",
}

EXT_KIND_MAP: dict[str, str] = {
    "xlsx": "spreadsheet", "xls": "spreadsheet", "csv": "spreadsheet",
    "docx": "document", "doc": "document",
    "pptx": "presentation", "ppt": "presentation",
    "pdf": "document",
    "txt": "document", "md": "document", "json": "document",
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image", "svg": "image",
    "mp4": "video", "avi": "video", "mov": "video",
    "mp3": "audio", "wav": "audio", "flac": "audio",
}


def _detect_kind(ext: str) -> str:
    return EXT_KIND_MAP.get(ext.lower(), "binary")


def _detect_mime(ext: str) -> str:
    ext = ext.lower()
    mime_map = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "csv": "text/csv",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pdf": "application/pdf",
        "txt": "text/plain", "md": "text/markdown", "json": "application/json",
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "svg": "image/svg+xml",
        "mp4": "video/mp4", "mp3": "audio/mpeg",
    }
    return mime_map.get(ext, "application/octet-stream")


async def _check_name_conflict(
    db: AsyncSession,
    owner_id: int,
    name: str,
    extension: str,
    folder_id: int | None,
    exclude_id: int | None = None,
) -> Artifact | None:
    conds = [
        Artifact.owner_id == owner_id,
        Artifact.name == name,
        Artifact.extension == extension,
        Artifact.folder_id == folder_id,
        Artifact.status == "active",
    ]
    if exclude_id:
        conds.append(Artifact.id != exclude_id)
    result = await db.execute(select(Artifact).where(*conds))
    return result.scalar_one_or_none()


async def _resolve_conflict(
    db: AsyncSession,
    existing: Artifact,
    conflict_policy: str,
    owner_id: int,
    name: str,
    extension: str,
    folder_id: int | None,
) -> tuple[str, str]:
    if conflict_policy == CONFLICT_FAIL:
        raise ConflictError(
            f"An artifact named '{name}.{extension}' already exists in this location"
        )
    if conflict_policy == CONFLICT_AUTO_RENAME:
        counter = 2
        while True:
            new_name = f"{name} {counter}"
            dup = await _check_name_conflict(db, owner_id, new_name, extension, folder_id)
            if not dup:
                return new_name, extension
            counter += 1
    if conflict_policy in (CONFLICT_OVERWRITE, CONFLICT_REPLACE_EXISTING):
        return name, extension
    if conflict_policy == CONFLICT_CREATE_VERSION:
        return name, extension
    return name, extension


async def create_artifact(
    db: AsyncSession,
    owner_id: int,
    name: str,
    extension: str = "",
    *,
    mime_type: str | None = None,
    kind: str | None = None,
    storage_mode: str = "file",
    content: bytes | None = None,
    content_json: dict | None = None,
    content_text: str | None = None,
    folder_id: int | None = None,
    source_module: str | None = None,
    source_object_type: str | None = None,
    source_object_id: int | None = None,
    conflict_policy: str = DEFAULT_CONFLICT_POLICY,
    file_id: int | None = None,
) -> dict[str, Any]:
    ext = extension.lower().lstrip(".")
    kind = kind or _detect_kind(ext)
    mime_type = mime_type or _detect_mime(ext)

    if not name:
        raise ValidationError("Artifact name is required")

    existing = await _check_name_conflict(db, owner_id, name, ext, folder_id)
    if existing and conflict_policy == CONFLICT_CREATE_VERSION:
        content_bytes = content or b""
        if file_id is not None:
            linked_file = await check_file_access(db, file_id, owner_id)
            existing.file_id = linked_file.id
            existing.storage_mode = "file" if not existing.content_json and not existing.content_text else "hybrid"
            existing.size = linked_file.size or len(content_bytes)
            existing.binary_hash = hashlib.sha256(content_bytes).hexdigest() if content_bytes else existing.binary_hash
            existing.source_module = source_module or existing.source_module
            existing.source_object_type = source_object_type or existing.source_object_type
            existing.source_object_id = source_object_id or existing.source_object_id
            await db.commit()
            await db.refresh(existing)
            await _record_operation(
                db, existing.id, "generic", None, "create_version",
                {"file_id": file_id, "source_module": source_module},
                created_by=owner_id,
            )
            await _create_version_snapshot(
                db, existing, "Created new version",
                created_by=owner_id,
            )
            return _artifact_to_dict(existing)
        return await replace_artifact_content(
            db,
            existing.id,
            owner_id,
            content=content_bytes or None,
            content_json=content_json,
            content_text=content_text,
            operation_type="create_version",
            operation_summary="Created new version",
            create_version=True,
        )

    resolved_name = name
    if existing:
        resolved_name, _ = await _resolve_conflict(
            db, existing, conflict_policy, owner_id, name, ext, folder_id
        )

    artifact = Artifact(
        owner_id=owner_id,
        name=resolved_name,
        extension=ext,
        mime_type=mime_type,
        kind=kind,
        storage_mode=storage_mode,
        folder_id=folder_id,
        source_module=source_module,
        source_object_type=source_object_type,
        source_object_id=source_object_id,
        status="active",
        size=0,
    )

    content_bytes = content or b""

    if file_id is not None:
        linked_file = await check_file_access(db, file_id, owner_id)
        artifact.file_id = linked_file.id
        artifact.size = linked_file.size or len(content_bytes)
        artifact.storage_mode = "file"
        artifact.binary_hash = hashlib.sha256(content_bytes).hexdigest() if content_bytes else None
    elif storage_mode == "file":
        try:
            upload_result = await upload_file(
                db,
                io.BytesIO(content_bytes),
                f"{resolved_name}.{ext}",
                owner_id,
                folder_id,
            )
            artifact.file_id = upload_result["id"]
            artifact.size = upload_result.get("size", len(content_bytes))
        except ConflictError:
            if conflict_policy == CONFLICT_REPLACE_EXISTING:
                existing_file = await _check_name_conflict_file(db, resolved_name, ext, folder_id, owner_id)
                if existing_file:
                    await replace_file_content(db, existing_file.id, owner_id, content_bytes)
                    artifact.file_id = existing_file.id
                    artifact.size = len(content_bytes)
                else:
                    raise
            else:
                raise
    elif storage_mode == "db":
        if content_json:
            artifact.content_json = json.dumps(content_json, ensure_ascii=False)
        if content_text:
            artifact.content_text = content_text
        artifact.size = len(content_json or {}) if content_json else 0

    if content_bytes:
        artifact.binary_hash = hashlib.sha256(content_bytes).hexdigest()

    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)

    await _record_operation(
        db, artifact.id, "generic", None, "create",
        {"name": name, "extension": ext, "storage_mode": storage_mode},
        created_by=owner_id,
    )

    await _create_version_snapshot(
        db, artifact, "Initial creation", created_by=owner_id
    )

    return _artifact_to_dict(artifact)


async def _check_name_conflict_file(
    db: AsyncSession, name: str, extension: str, folder_id: int | None, owner_id: int
) -> File | None:
    from app.models.file import File
    result = await db.execute(
        select(File).where(
            File.name == name,
            File.extension == extension,
            File.folder_id == folder_id,
            File.owner_id == owner_id,
            File.deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def get_artifact(db: AsyncSession, artifact_id: int, owner_id: int | None = None) -> dict[str, Any]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Artifact not found")
    if owner_id is not None and artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")
    return _artifact_to_dict(artifact)


async def list_artifacts(
    db: AsyncSession,
    owner_id: int,
    folder_id: int | None = None,
    kind: str | None = None,
    extension: str | None = None,
    status: str = "active",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    conds = [Artifact.owner_id == owner_id, Artifact.status == status]
    if folder_id is not None:
        conds.append(Artifact.folder_id == folder_id)
    if kind:
        conds.append(Artifact.kind == kind)
    if extension:
        conds.append(Artifact.extension == extension)

    total_q = select(func.count(Artifact.id)).where(*conds)
    total = await db.scalar(total_q) or 0

    q = (
        select(Artifact)
        .where(*conds)
        .order_by(Artifact.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(q)
    items = [_artifact_to_dict(a) for a in result.scalars().all()]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def update_artifact_metadata(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
    *,
    name: str | None = None,
    folder_id: int | None = None,
    conflict_policy: str = DEFAULT_CONFLICT_POLICY,
) -> dict[str, Any]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Artifact not found")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    if name is not None:
        existing = await _check_name_conflict(
            db, owner_id, name, artifact.extension, artifact.folder_id, exclude_id=artifact_id
        )
        if existing:
            resolved_name, _ = await _resolve_conflict(
                db, existing, conflict_policy, owner_id,
                name, artifact.extension, artifact.folder_id,
            )
            artifact.name = resolved_name
        else:
            artifact.name = name

    if folder_id is not None:
        artifact.folder_id = folder_id

    await db.commit()
    await db.refresh(artifact)
    return _artifact_to_dict(artifact)


async def replace_artifact_content(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
    *,
    content: bytes | None = None,
    content_json: dict | None = None,
    content_text: str | None = None,
    operation_type: str = "update",
    operation_summary: str = "",
    create_version: bool = True,
) -> dict[str, Any]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Artifact not found")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    if content is not None:
        if artifact.storage_mode == "file" or artifact.file_id:
            result = await replace_file_content(db, artifact.file_id, owner_id, content) if artifact.file_id else None
            if result:
                artifact.size = result.get("size", len(content))
                artifact.binary_hash = hashlib.sha256(content).hexdigest()
        else:
            content_bytes = content
            try:
                result = await upload_file(
                    db,
                    io.BytesIO(content_bytes),
                    f"{artifact.name}.{artifact.extension}",
                    owner_id,
                    artifact.folder_id,
                )
                artifact.file_id = result["id"]
                artifact.storage_mode = "file"
                artifact.size = result.get("size", len(content_bytes))
                artifact.binary_hash = hashlib.sha256(content_bytes).hexdigest()
            except ConflictError:
                result = await replace_file_content(db, artifact.file_id, owner_id, content_bytes) if artifact.file_id else None
                if result:
                    artifact.size = len(content_bytes)
                    artifact.binary_hash = hashlib.sha256(content_bytes).hexdigest()

    if content_json is not None:
        artifact.content_json = json.dumps(content_json, ensure_ascii=False)
        if artifact.storage_mode == "db":
            artifact.storage_mode = "hybrid"

    if content_text is not None:
        artifact.content_text = content_text

    await db.commit()
    await db.refresh(artifact)

    await _record_operation(
        db, artifact.id, "generic", None, operation_type,
        {"summary": operation_summary},
        created_by=owner_id,
    )

    if create_version:
        await _create_version_snapshot(
            db, artifact, operation_summary or operation_type,
            created_by=owner_id,
        )

    return _artifact_to_dict(artifact)


async def delete_artifact(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
    *,
    soft: bool = True,
) -> dict[str, Any]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Artifact not found")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    if soft:
        artifact.status = "deleted"
        artifact.deleted_at = datetime.now(timezone.utc)
        await db.commit()
    else:
        await db.delete(artifact)
        await db.commit()

    return {"success": True, "artifact_id": artifact_id, "soft": soft}


async def restore_artifact(db: AsyncSession, artifact_id: int, owner_id: int) -> dict[str, Any]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status != "deleted":
        raise NotFound("Artifact not found or not deleted")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    artifact.status = "active"
    artifact.deleted_at = None
    await db.commit()
    await db.refresh(artifact)

    await _record_operation(
        db, artifact.id, "generic", None, "restore", {},
        created_by=owner_id,
    )

    return _artifact_to_dict(artifact)


async def rename_artifact(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
    new_name: str,
    conflict_policy: str = DEFAULT_CONFLICT_POLICY,
) -> dict[str, Any]:
    return await update_artifact_metadata(
        db, artifact_id, owner_id,
        name=new_name,
        conflict_policy=conflict_policy,
    )


async def copy_artifact(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
    *,
    target_folder_id: int | None = None,
    new_name: str | None = None,
    conflict_policy: str = DEFAULT_CONFLICT_POLICY,
) -> dict[str, Any]:
    original = await db.get(Artifact, artifact_id)
    if not original or original.status == "deleted":
        raise NotFound("Artifact not found")
    if original.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    dest_name = new_name or original.name
    folder = target_folder_id if target_folder_id is not None else original.folder_id

    existing = await _check_name_conflict(db, owner_id, dest_name, original.extension, folder)
    if existing:
        resolved_name, _ = await _resolve_conflict(
            db, existing, conflict_policy, owner_id,
            dest_name, original.extension, folder,
        )
        dest_name = resolved_name

    content_bytes = None
    if original.file_id:
        try:
            content_bytes = await get_file_content_bytes(original.file_id, owner_id)
        except Exception:
            pass

    return await create_artifact(
        db, owner_id,
        name=dest_name,
        extension=original.extension,
        mime_type=original.mime_type,
        kind=original.kind,
        storage_mode=original.storage_mode,
        content=content_bytes,
        content_json=json.loads(original.content_json) if original.content_json else None,
        content_text=original.content_text,
        folder_id=folder,
        source_module="artifact_service",
        source_object_type="copy",
        source_object_id=original.id,
        conflict_policy=CONFLICT_FAIL,
    )


async def move_artifact(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
    target_folder_id: int | None,
    conflict_policy: str = DEFAULT_CONFLICT_POLICY,
) -> dict[str, Any]:
    return await update_artifact_metadata(
        db, artifact_id, owner_id,
        folder_id=target_folder_id,
        conflict_policy=conflict_policy,
    )


async def create_artifact_version(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
    *,
    operation_summary: str = "",
) -> dict[str, Any]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Artifact not found")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    version = await _create_version_snapshot(
        db, artifact, operation_summary, created_by=owner_id,
    )
    return _version_to_dict(version)


async def list_artifact_versions(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
) -> list[dict[str, Any]]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Artifact not found")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    result = await db.execute(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .order_by(ArtifactVersion.version_no.desc())
    )
    return [_version_to_dict(v) for v in result.scalars().all()]


async def restore_artifact_version(
    db: AsyncSession,
    artifact_id: int,
    version_id: int,
    owner_id: int,
) -> dict[str, Any]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Artifact not found")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    version = await db.get(ArtifactVersion, version_id)
    if not version or version.artifact_id != artifact_id:
        raise NotFound("Version not found")

    if version.snapshot_json:
        try:
            snapshot = json.loads(version.snapshot_json)
            content_json = snapshot.get("content_json") or snapshot.get("cells")
            if isinstance(content_json, dict):
                artifact.content_json = json.dumps(content_json, ensure_ascii=False)
            if snapshot.get("content_text"):
                artifact.content_text = snapshot["content_text"]
        except (json.JSONDecodeError, TypeError):
            pass

    if version.file_id:
        artifact.file_id = version.file_id
        artifact.storage_mode = "file" if not artifact.content_json and not artifact.content_text else "hybrid"
    artifact.size = version.size
    artifact.binary_hash = version.binary_hash

    await db.commit()
    await db.refresh(artifact)

    await _record_operation(
        db, artifact.id, "generic", None, "restore_version",
        {"version_id": version_id, "version_no": version.version_no},
        created_by=owner_id,
    )

    return _artifact_to_dict(artifact)


async def export_artifact(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
    *,
    target_format: str | None = None,
) -> dict[str, Any]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Artifact not found")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    if artifact.file_id:
        return {
            "artifact_id": artifact.id,
            "file_id": artifact.file_id,
            "url": f"/api/files/download/{artifact.file_id}",
            "name": f"{artifact.name}.{artifact.extension}",
            "size": artifact.size,
        }

    if artifact.content_json:
        ext = target_format or artifact.extension or "json"
        content_bytes = artifact.content_text or artifact.content_json
        if isinstance(content_bytes, str):
            content_bytes = content_bytes.encode("utf-8")

        try:
            result = await upload_file(
                db,
                io.BytesIO(content_bytes),
                f"{artifact.name}.{ext}",
                owner_id,
                artifact.folder_id,
            )
            artifact.file_id = result["id"]
            artifact.storage_mode = "hybrid"
            artifact.size = len(content_bytes)
            artifact.binary_hash = hashlib.sha256(content_bytes).hexdigest()
            await db.commit()

            return {
                "artifact_id": artifact.id,
                "file_id": result["id"],
                "url": f"/api/files/download/{result['id']}",
                "name": f"{artifact.name}.{ext}",
                "size": len(content_bytes),
            }
        except Exception as e:
            raise ValidationError(f"Export failed: {e}")

    raise ValidationError("No content to export")


async def publish_artifact(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
    *,
    target_file_id: int | None = None,
    conflict_policy: str = DEFAULT_CONFLICT_POLICY,
) -> dict[str, Any]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Artifact not found")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    if target_file_id:
        target = await check_file_access(db, target_file_id, owner_id)
        existing_name = target.name
        existing_ext = target.extension or artifact.extension

        if artifact.file_id:
            from app.services.file_upload_service import replace_file_content as replace_content
            content_bytes = await get_file_content_bytes(artifact.file_id, owner_id)
            result = await replace_content(db, target_file_id, owner_id, content_bytes)
            artifact.file_id = target_file_id
            artifact.size = result.get("size", len(content_bytes))
            artifact.binary_hash = hashlib.sha256(content_bytes).hexdigest()
            await db.commit()
            await _record_operation(
                db, artifact.id, "generic", None, "publish_replace",
                {"target_file_id": target_file_id},
                created_by=owner_id,
            )
            await _create_version_snapshot(
                db, artifact, "Published to existing file",
                created_by=owner_id,
            )
            return {
                "success": True,
                "artifact_id": artifact.id,
                "file_id": target_file_id,
                "name": f"{existing_name}.{existing_ext}",
                "status": "replaced",
                "published": True,
            }

    export_result = await export_artifact(db, artifact_id, owner_id)

    return {
        "success": True,
        "artifact_id": artifact.id,
        "file_id": export_result.get("file_id"),
        "name": export_result.get("name"),
        "status": "published",
        "published": True,
    }


async def replace_file_from_artifact(
    db: AsyncSession,
    owner_id: int,
    target_file_id: int,
    source_artifact_id: int,
    *,
    conflict_policy: str = DEFAULT_CONFLICT_POLICY,
) -> dict[str, Any]:
    await check_file_access(db, target_file_id, owner_id)
    artifact = await db.get(Artifact, source_artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Source artifact not found")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied for artifact")

    content_bytes = None
    if artifact.file_id:
        content_bytes = await get_file_content_bytes(artifact.file_id, owner_id)
    elif artifact.content_json:
        content_bytes = artifact.content_json.encode("utf-8")
    elif artifact.content_text:
        content_bytes = artifact.content_text.encode("utf-8")

    if not content_bytes:
        raise ValidationError("Artifact has no content to replace with")

    from app.services.file_upload_service import replace_file_content as replace_content
    result = await replace_content(db, target_file_id, owner_id, content_bytes)

    await _record_operation(
        db, artifact.id, "generic", None, "replace_file",
        {"target_file_id": target_file_id},
        created_by=owner_id,
    )
    artifact.file_id = target_file_id
    artifact.size = result.get("size", len(content_bytes))
    artifact.binary_hash = hashlib.sha256(content_bytes).hexdigest()
    await db.commit()
    await _create_version_snapshot(
        db, artifact, "Replaced desktop file",
        created_by=owner_id,
    )

    return {
        "success": True,
        "target_file_id": target_file_id,
        "source_artifact_id": source_artifact_id,
        "new_file_id": result["id"],
        "size": result["size"],
    }


async def list_operations(
    db: AsyncSession,
    artifact_id: int,
    owner_id: int,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact or artifact.status == "deleted":
        raise NotFound("Artifact not found")
    if artifact.owner_id != owner_id:
        raise PermissionDenied("Permission denied")

    total_q = select(func.count(ArtifactOperation.id)).where(
        ArtifactOperation.artifact_id == artifact_id
    )
    total = await db.scalar(total_q) or 0

    q = (
        select(ArtifactOperation)
        .where(ArtifactOperation.artifact_id == artifact_id)
        .order_by(ArtifactOperation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(q)
    items = [_operation_to_dict(op) for op in result.scalars().all()]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def _record_operation(
    db: AsyncSession,
    artifact_id: int,
    object_type: str,
    object_id: int | None,
    operation_type: str,
    payload: dict | None = None,
    *,
    created_by: int = 0,
):
    op = ArtifactOperation(
        artifact_id=artifact_id,
        object_type=object_type,
        object_id=object_id,
        operation_type=operation_type,
        payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        created_by=created_by,
    )
    db.add(op)
    await db.commit()


async def _create_version_snapshot(
    db: AsyncSession,
    artifact: Artifact,
    operation_summary: str = "",
    *,
    created_by: int = 0,
) -> ArtifactVersion:
    result = await db.execute(
        select(func.coalesce(func.max(ArtifactVersion.version_no), 0))
        .where(ArtifactVersion.artifact_id == artifact.id)
    )
    max_no = result.scalar() or 0

    snapshot = {}
    if artifact.content_json:
        try:
            snapshot["content_json"] = json.loads(artifact.content_json)
        except (json.JSONDecodeError, TypeError):
            snapshot["content_json"] = artifact.content_json
    if artifact.content_text:
        snapshot["content_text"] = artifact.content_text

    version = ArtifactVersion(
        artifact_id=artifact.id,
        version_no=max_no + 1,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False) if snapshot else None,
        file_id=artifact.file_id,
        binary_hash=artifact.binary_hash,
        size=artifact.size,
        operation_summary=operation_summary or "",
        created_by=created_by,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)

    artifact.current_version_id = version.id
    await db.commit()

    return version


def _artifact_to_dict(a: Artifact) -> dict[str, Any]:
    package_id = a.source_object_id if a.source_object_type == "content_package" else None
    download_url = f"/api/files/download/{a.file_id}" if a.file_id else None
    open_url = f"/api/files/preview/{a.file_id}" if a.file_id else None
    return {
        "id": a.id,
        "artifact_id": a.id,
        "owner_id": a.owner_id,
        "name": a.name,
        "extension": a.extension,
        "mime_type": a.mime_type,
        "kind": a.kind,
        "storage_mode": a.storage_mode,
        "file_id": a.file_id,
        "content_json": json.loads(a.content_json) if a.content_json else None,
        "content_text": a.content_text,
        "binary_hash": a.binary_hash,
        "size": a.size,
        "status": a.status,
        "source_module": a.source_module,
        "origin_module": a.source_module,
        "source_object_type": a.source_object_type,
        "source_object_id": a.source_object_id,
        "package_id": package_id,
        "download_url": download_url,
        "open_url": open_url,
        "current_version_id": a.current_version_id,
        "folder_id": a.folder_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "deleted_at": a.deleted_at.isoformat() if a.deleted_at else None,
    }


def _version_to_dict(v: ArtifactVersion) -> dict[str, Any]:
    return {
        "id": v.id,
        "artifact_id": v.artifact_id,
        "version_no": v.version_no,
        "snapshot_json": json.loads(v.snapshot_json) if v.snapshot_json else None,
        "file_id": v.file_id,
        "storage_path": v.storage_path,
        "binary_hash": v.binary_hash,
        "size": v.size,
        "operation_summary": v.operation_summary,
        "created_by": v.created_by,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _operation_to_dict(op: ArtifactOperation) -> dict[str, Any]:
    return {
        "id": op.id,
        "artifact_id": op.artifact_id,
        "object_type": op.object_type,
        "object_id": op.object_id,
        "operation_type": op.operation_type,
        "payload_json": json.loads(op.payload_json) if op.payload_json else None,
        "inverse_payload_json": json.loads(op.inverse_payload_json) if op.inverse_payload_json else None,
        "snapshot_json": json.loads(op.snapshot_json) if op.snapshot_json else None,
        "created_by": op.created_by,
        "created_at": op.created_at.isoformat() if op.created_at else None,
    }
