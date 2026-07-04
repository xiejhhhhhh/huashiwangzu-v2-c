"""Content IR writer — writes validated, normalized IR to canonical DB source.

Dispatch rules:
  document/presentation/text/mixed  → ContentPackage + ContentPackageVersion
  spreadsheet                       → excel-engine (via call_capability)
  image                             → Resource + ResourceRef
  memory                            → memory capability (via call_capability)
"""
import base64
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, PermissionDenied
from app.core.exceptions import ValidationError as AppValidationError
from app.models.content import ContentPackage, ContentPackageVersion
from app.models.file import File
from app.models.file_share import FileShare
from app.services.content.ir_normalizer import normalize_ir
from app.services.content.ir_validator import validate_ir
from app.services.content.resource_service import ResourceService
from app.services.file_service import check_file_access
from app.services.module_registry import call_capability

logger = logging.getLogger("v2.content").getChild("ir_writer")


async def write_ir(
    db: AsyncSession,
    content_ir: dict[str, Any],
    owner_id: int,
    caller: str,
    source_file_id: int | None = None,
    expected_version_id: int | None = None,
) -> dict[str, Any]:
    """Write a Content IR to the canonical DB source.

    Args:
        db: Database session.
        content_ir: The validated and normalized Content IR dict.
        owner_id: User ID of the content owner.
        caller: Caller string (e.g. 'user:123').
        source_file_id: Optional source file record ID.
        expected_version_id: For version conflict detection.

    Returns:
        Dict with success status and canonical source info.

    Raises:
        ValidationError: If IR fails validation.
        ConflictError: If expected_version_id does not match.
    """
    # Always validate first (even if caller claims pre-validated)
    validation = await validate_ir(content_ir)
    if not validation.valid:
        raise AppValidationError(
            "Content IR validation failed",
            details=[e.model_dump() for e in validation.errors],
        )

    source_file_id = _normalize_source_file_id(source_file_id or content_ir.get("source_file_id"))
    if source_file_id is not None:
        source_file = await _check_source_file_write_access(
            db,
            source_file_id,
            owner_id,
        )
        package_owner_id = source_file.owner_id
    else:
        package_owner_id = owner_id

    # Normalize
    ir = await normalize_ir(content_ir)
    content_type = ir.get("content_type", "")

    if content_type in ("document", "presentation", "text", "mixed"):
        return await _write_to_content_package(
            db,
            ir,
            owner_id,
            package_owner_id,
            source_file_id,
            expected_version_id,
        )
    elif content_type == "spreadsheet":
        return await _write_to_excel_engine(ir, owner_id, caller)
    elif content_type == "image":
        return await _write_to_resource(db, ir, owner_id, source_file_id)
    elif content_type == "memory":
        return await _write_to_memory(ir, owner_id, caller)
    else:
        raise AppValidationError(f"Unsupported content_type: {content_type}")


async def _write_to_content_package(
    db: AsyncSession,
    ir: dict[str, Any],
    writer_id: int,
    package_owner_id: int,
    source_file_id: int | None,
    expected_version_id: int | None,
) -> dict[str, Any]:
    blocks = ir.get("blocks", [])
    resources = ir.get("resources", [])

    # Find existing or create new package
    if source_file_id:
        existing = await db.execute(
            select(ContentPackage).where(
                ContentPackage.source_file_id == source_file_id,
                ContentPackage.owner_id == package_owner_id,
                ContentPackage.deleted.is_(False),
            ).order_by(ContentPackage.created_at.desc()).limit(1)
        )
        pkg = existing.scalar_one_or_none()
        if not pkg:
            pkg = ContentPackage(
                owner_id=package_owner_id,
                source_file_id=source_file_id,
                package_type=ir.get("content_type", "document"),
                source_extension="",
                origin_type="generated",
                package_version=ir.get("schema_version", "1.0"),
                status="parsed",
            )
            db.add(pkg)
            await db.flush()
    else:
        # Always create new ContentPackage when no source_file_id and no package_id
        # This prevents accidental reuse of orphaned packages.
        pkg = ContentPackage(
            owner_id=package_owner_id,
            source_file_id=None,
            package_type=ir.get("content_type", "document"),
            source_extension="",
            origin_type="generated",
            package_version=ir.get("schema_version", "1.0"),
            status="parsed",
        )
        db.add(pkg)
        await db.flush()

    # Version conflict detection
    if expected_version_id is not None:
        if pkg.current_version_id != expected_version_id:
            raise ConflictError(
                f"Version conflict: expected {expected_version_id}, "
                f"current is {pkg.current_version_id}"
            )

    # Compute version_no
    version_no = 1
    if pkg.current_version_id:
        current_ver = await db.get(ContentPackageVersion, pkg.current_version_id)
        if current_ver:
            version_no = current_ver.version_no + 1
    else:
        existing_ver = await db.execute(
            select(ContentPackageVersion).where(
                ContentPackageVersion.package_id == pkg.id,
            ).order_by(ContentPackageVersion.version_no.desc()).limit(1)
        )
        ev = existing_ver.scalar_one_or_none()
        if ev:
            version_no = ev.version_no + 1

    resources_for_json, refs_to_add = await _persist_package_resources(
        db,
        resources,
        blocks,
        writer_id,
    )

    # Build content_json (backward-compatible shape)
    manifest_dict = {
        "title": ir.get("title", ""),
        "source_file_id": source_file_id,
        "source_module": ir.get("source_module", ""),
        "parser": ir.get("parser", ""),
        "package_type": ir.get("content_type", ""),
        "schema_version": ir.get("schema_version", "1.0"),
        "locale": ir.get("locale", "zh-CN"),
    }
    content_json = {
        "manifest": manifest_dict,
        "blocks": blocks,
    }
    metadata = ir.get("metadata")
    if metadata:
        content_json["metadata"] = metadata
    if resources_for_json:
        content_json["resources"] = resources_for_json
        content_json["assets"] = resources_for_json
    if ir.get("warnings"):
        content_json["warnings"] = ir.get("warnings")
    if ir.get("quality"):
        content_json["quality"] = ir.get("quality")

    content_json_str = json.dumps(
        content_json,
        ensure_ascii=False,
    )

    version = ContentPackageVersion(
        package_id=pkg.id,
        version_no=version_no,
        content_json=content_json_str,
        summary=f"Written via write_ir ({ir.get('content_type', '')})",
        operation_type="write_ir",
        created_by=writer_id,
    )
    db.add(version)
    await db.flush()

    if refs_to_add:
        resource_svc = ResourceService()
        for ref in refs_to_add:
            await resource_svc.add_ref(
                db,
                pkg.id,
                ref["resource_id"],
                block_id=ref.get("block_id"),
                usage_hints=ref.get("usage_hints"),
                version_id=version.id,
            )

    pkg.current_version_id = version.id
    pkg.manifest_json = json.dumps(manifest_dict, ensure_ascii=False)
    pkg.status = "parsed"
    await db.commit()
    await db.refresh(pkg)

    return {
        "canonical_source": "content_package",
        "package_id": pkg.id,
        "version_id": version.id,
        "version_no": version_no,
        "owner_id": package_owner_id,
        "written_by": writer_id,
    }


def _normalize_source_file_id(source_file_id: int | str | None) -> int | None:
    if source_file_id is None:
        return None
    try:
        normalized = int(source_file_id)
    except (TypeError, ValueError) as exc:
        raise AppValidationError("source_file_id must be a positive integer") from exc
    if normalized <= 0:
        raise AppValidationError("source_file_id must be a positive integer")
    return normalized


async def _check_source_file_write_access(
    db: AsyncSession,
    source_file_id: int,
    user_id: int,
) -> File:
    """Return the source file only when the caller can write content for it."""
    file_record = await check_file_access(db, source_file_id, user_id)
    if file_record.owner_id == user_id:
        return file_record

    share = await db.scalar(
        select(FileShare).where(
            FileShare.file_id == source_file_id,
            FileShare.shared_with_user_id == user_id,
            FileShare.permission == "edit",
        )
    )
    if not share:
        raise PermissionDenied("Edit permission required to write Content IR for shared file")
    return file_record


async def _persist_package_resources(
    db: AsyncSession,
    resources: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    owner_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not resources:
        return [], []

    resource_svc = ResourceService()
    resources_for_json: list[dict[str, Any]] = []
    local_to_real: dict[str, int] = {}
    resource_hints: dict[int, str] = {}

    for res in resources:
        resource_entry = {k: v for k, v in res.items() if k != "data_b64"}
        data_b64 = res.get("data_b64")
        if data_b64:
            try:
                data = base64.b64decode(data_b64, validate=True)
            except (TypeError, ValueError) as exc:
                raise AppValidationError("Invalid resource data_b64") from exc
            stored = await resource_svc.create_resource(
                db,
                data,
                owner_id=owner_id,
                resource_type=res.get("resource_type", "image"),
                mime_type=res.get("mime_type", "application/octet-stream"),
                filename=res.get("filename", "resource.bin"),
                width=res.get("width"),
                height=res.get("height"),
                description=res.get("description"),
                ocr_text=res.get("ocr_text"),
            )
            local_id = res.get("id")
            if local_id is not None:
                local_to_real[str(local_id)] = stored["id"]
            resource_entry.update({
                "resource_id": stored["id"],
                "hash": stored.get("hash"),
                "storage_path": stored.get("storage_path"),
                "file_size": stored.get("file_size"),
            })
            resource_hints[stored["id"]] = str(res.get("description") or res.get("filename") or "")
            if res.get("vlm_metadata"):
                await resource_svc.update_description(
                    db,
                    stored["id"],
                    vlm_metadata=res["vlm_metadata"],
                )
        resources_for_json.append(resource_entry)

    refs_to_add: list[dict[str, Any]] = []
    block_refs = _replace_block_resource_refs(blocks, local_to_real)
    seen_resource_ids: set[int] = set()
    for local_id, resource_id in local_to_real.items():
        if resource_id in seen_resource_ids:
            continue
        seen_resource_ids.add(resource_id)
        refs_to_add.append({
            "resource_id": resource_id,
            "block_id": block_refs.get(local_id),
            "usage_hints": resource_hints.get(resource_id, ""),
        })

    return resources_for_json, refs_to_add


def _replace_block_resource_refs(
    blocks: list[dict[str, Any]],
    local_to_real: dict[str, int],
) -> dict[str, str | None]:
    block_refs: dict[str, str | None] = {}

    def _walk(items: list[dict[str, Any]]) -> None:
        for block in items:
            ref = block.get("resource_ref")
            ref_key = str(ref) if ref is not None else None
            if ref_key is not None and ref_key in local_to_real:
                block_refs.setdefault(ref_key, block.get("id"))
                block["resource_ref"] = local_to_real[ref_key]
            children = block.get("children")
            if isinstance(children, list):
                _walk(children)

    _walk(blocks)
    return block_refs


async def _write_to_excel_engine(
    ir: dict[str, Any],
    owner_id: int,
    caller: str,
) -> dict[str, Any]:
    """Write spreadsheet IR to excel-engine via cross-module call."""
    blocks = ir.get("blocks", [])
    sheet_name = ir.get("title", "Sheet1")

    # Create workbook in excel-engine
    result = await call_capability(
        "excel-engine", "create_workbook",
        {"name": sheet_name},
        caller,
        caller_role="editor",
    )
    state_key = result.get("state_key", "")

    # Convert IR blocks to rows and write via update_range
    for block in blocks:
        if block.get("type") == "sheet":
            sheet_name_block = block.get("text", sheet_name)
            children = block.get("children", [])
            for child in children:
                if child.get("type") == "table":
                    data = child.get("data", {})
                    headers = data.get("headers", [])
                    rows = data.get("rows", [])
                    all_rows = []
                    start_cell = data.get("start_cell", "A1")

                    # Parse start_cell to extract start_row/start_col
                    start_row = 0
                    start_col = 0
                    if start_cell:
                        import re
                        m = re.match(r'^([A-Za-z]+)(\d+)$', str(start_cell))
                        if m:
                            col_str = m.group(1).upper()
                            start_col = 0
                            for c in col_str:
                                start_col = start_col * 26 + (ord(c) - ord('A') + 1)
                            start_col -= 1  # 0-based
                            start_row = int(m.group(2)) - 1  # 0-based

                    if headers:
                        all_rows.append(headers)
                    if rows:
                        all_rows.extend(rows)

                    if all_rows:
                        await call_capability(
                            "excel-engine", "update_range",
                            {
                                "state_key": state_key,
                                "sheet": sheet_name_block,
                                "start_row": start_row,
                                "start_col": start_col,
                                "rows": all_rows,
                            },
                            caller,
                            caller_role="editor",
                        )

    return {
        "canonical_source": "excel_engine",
        "state_key": state_key,
        "owner_id": owner_id,
    }


async def _write_to_resource(
    db: AsyncSession,
    ir: dict[str, Any],
    owner_id: int,
    source_file_id: int | None,
) -> dict[str, Any]:
    """Write image IR to Resource via call_capability to content:store_resource."""
    resources = ir.get("resources", [])
    if not resources:
        from app.core.exceptions import ValidationError as AppVE
        raise AppVE("Image IR must have at least one resource")

    created_ids = []
    for res in resources:
        data_b64 = res.get("data_b64", "")
        result = await call_capability(
            "content", "store_resource",
            {
                "data_b64": data_b64,
                "resource_type": res.get("resource_type", "image"),
                "mime_type": res.get("mime_type", "image/png"),
                "filename": res.get("filename", "image.png"),
                "description": res.get("description"),
                "ocr_text": res.get("ocr_text"),
                "vlm_metadata": res.get("vlm_metadata"),
                "file_id": source_file_id,
            },
            f"user:{owner_id}",
            caller_role="editor",
        )
        inner = result.get("data", result) if isinstance(result, dict) else {}
        if isinstance(inner, dict) and inner.get("id"):
            created_ids.append(inner["id"])

    return {
        "canonical_source": "resource",
        "resource_ids": created_ids,
        "owner_id": owner_id,
    }


async def _write_to_memory(
    ir: dict[str, Any],
    owner_id: int,
    caller: str,
) -> dict[str, Any]:
    """Write memory IR to memory module via cross-module call."""
    lines = []
    blocks = ir.get("blocks", [])
    for block in blocks:
        text = block.get("text", "")
        if text:
            lines.append(text)

    full_text = "\n".join(lines) if lines else ir.get("title", "")
    if not full_text:
        from app.core.exceptions import ValidationError as AppVE
        raise AppVE("Memory IR must have text content")

    result = await call_capability(
        "memory", "save",
        {"text": full_text, "tags": str(ir.get("title", "")), "source": "content:write_ir"},
        caller,
        caller_role="editor",
    )

    return {
        "canonical_source": "memory",
        "memory_id": result.get("id") if isinstance(result, dict) else None,
        "owner_id": owner_id,
    }
