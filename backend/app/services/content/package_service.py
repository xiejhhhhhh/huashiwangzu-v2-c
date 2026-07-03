"""Content Package service — the canonical source for structured content.

All structured content operations go through this service.
Agent, Knowledge, and Export all consume Content Packages.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFound, PermissionDenied, ValidationError
from app.models.content import (
    ContentPackage,
    ContentPackageVersion,
    Resource,
    ResourceRef,
)
from app.schemas.content_package import (
    BlockAppendRequest,
    BlockUpdateRequest,
    ReplaceTextRequest,
)
from app.services.content.resource_service import ResourceService
from app.services.file_service import check_file_access, get_file_record
from app.services.module_registry import call_capability

logger = logging.getLogger("v2.content").getChild("package")

PACKAGE_TYPE_MAP = {
    "docx": "document", "doc": "document",
    "xlsx": "spreadsheet", "xls": "spreadsheet", "csv": "spreadsheet",
    "pptx": "presentation", "ppt": "presentation",
    "pdf": "pdf",
    "txt": "text", "md": "text", "markdown": "text",
    "json": "text", "yaml": "text", "yml": "text",
    "png": "image", "jpg": "image", "jpeg": "image",
    "gif": "image", "bmp": "image", "webp": "image",
    "svg": "image",
    "mp4": "media", "avi": "media", "mov": "media",
    "mkv": "media", "webm": "media",
    "mp3": "media", "wav": "media", "flac": "media",
}

FORMAT_PARSER_MAP: dict[str, tuple[str, str]] = {
    "pdf": ("pdf-parser", "parse"),
    "docx": ("docx-parser", "parse"),
    "pptx": ("pptx-parser", "parse"),
    "xlsx": ("xlsx-parser", "parse"),
    "csv": ("csv-parser", "parse"),
    "tsv": ("csv-parser", "parse"),
    "txt": ("text-parser", "parse"),
    "md": ("markdown-parser", "parse"),
    "markdown": ("markdown-parser", "parse"),
    "json": ("structured-parser", "parse"),
    "yaml": ("structured-parser", "parse"),
    "yml": ("structured-parser", "parse"),
    "eml": ("email-parser", "parse"),
    "msg": ("email-parser", "parse"),
}

IMAGE_FORMATS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "svg"}
CONSUMABLE_PACKAGE_STATUSES = ("parsed", "degraded", "partial")
DEGRADED_RESOURCE_STATUSES = {"failed", "degraded", "partial", "done_with_errors"}


def _detect_package_type(extension: str) -> str:
    ext = extension.lower().strip(".")
    return PACKAGE_TYPE_MAP.get(ext, "generic")


def _get_parser_for_format(extension: str) -> tuple[str, str] | None:
    ext = extension.lower().strip(".")
    if ext in FORMAT_PARSER_MAP:
        return FORMAT_PARSER_MAP[ext]
    if ext in IMAGE_FORMATS:
        return ("image-vision", "describe")
    return None


def _ensure_block_ids(blocks: list[dict]) -> list[dict]:
    for i, b in enumerate(blocks):
        if not b.get("id"):
            raw = f"{i}:{b.get('text','')}:{b.get('type','')}"
            b["id"] = f"b{hashlib.md5(raw.encode()).hexdigest()[:12]}"
        if b.get("children"):
            _ensure_block_ids(b["children"])
    return blocks


def _iter_all_blocks(blocks: list[dict]) -> list[dict]:
    result: list[dict] = []
    stack = list(blocks)
    while stack:
        b = stack.pop(0)
        result.append(b)
        if b.get("children"):
            stack = b["children"] + stack
    return result


def _compute_package_parse_status(resource_diagnostics: list[dict]) -> str:
    if not isinstance(resource_diagnostics, list) or not resource_diagnostics:
        return "parsed"
    if any(d.get("status") in DEGRADED_RESOURCE_STATUSES for d in resource_diagnostics):
        return "degraded"
    return "parsed"


def is_package_consumable_status(status: object) -> bool:
    return str(status or "") in CONSUMABLE_PACKAGE_STATUSES


class ContentPackageService:

    async def get_or_create(
        self, db: AsyncSession, file_id: int, owner_id: int, caller: str,
        origin_type: str = "uploaded",
    ) -> dict[str, Any]:
        file_record = await get_file_record(db, file_id)
        if not file_record:
            raise NotFound(f"File {file_id} not found")
        await check_file_access(db, file_id, owner_id)

        existing = await self._find_active_by_file(db, file_id)
        if existing:
            return self._package_to_dict(existing)

        ext = (file_record.extension or "").lower()
        pkg_type = _detect_package_type(ext)

        pkg = ContentPackage(
            owner_id=file_record.owner_id,
            source_file_id=file_id,
            package_type=pkg_type,
            source_extension=ext,
            origin_type=origin_type,
            package_version="1.0",
            status="pending",
        )
        db.add(pkg)
        await db.commit()
        await db.refresh(pkg)
        return self._package_to_dict(pkg)

    async def run_pipeline(
        self, db: AsyncSession, package_id: int, caller: str,
    ) -> dict[str, Any]:
        pkg = await db.get(ContentPackage, package_id)
        if not pkg or pkg.deleted:
            raise NotFound(f"ContentPackage {package_id} not found")

        if not pkg.source_file_id:
            raise ValidationError("Package has no source file")

        file_record = await get_file_record(db, pkg.source_file_id)
        if not file_record:
            raise NotFound(f"Source file {pkg.source_file_id} not found")

        ext = (file_record.extension or "").lower()
        parser = _get_parser_for_format(ext)
        if not parser:
            pkg.status = "failed"
            pkg.parse_error = f"No parser for format: {ext}"
            await db.commit()
            raise ValidationError(pkg.parse_error)

        module_key, action = parser
        logger.info(
            "Content pipeline: package_id=%d file_id=%d via %s:%s",
            package_id, pkg.source_file_id, module_key, action,
        )

        try:
            result = await call_capability(
                module_key, action,
                {"file_id": pkg.source_file_id},
                caller,
            )
        except Exception as e:
            pkg.status = "failed"
            pkg.parse_error = str(e)
            await db.commit()
            raise

        raw_blocks = []
        raw_resources = []
        resource_diagnostics = []
        if isinstance(result, dict):
            raw_blocks = result.get("blocks", [])
            raw_resources = result.get("resources", [])
            resource_diagnostics = result.get("resource_diagnostics", [])

        raw_blocks = _ensure_block_ids(raw_blocks)

        # Save embedded resources and replace local IDs with real resource IDs
        resource_svc = ResourceService()
        local_to_real: dict[int, int] = {}
        for res in raw_resources:
            local_id = res.get("id") or res.get("resource_id")
            stored_resource_id = res.get("stored_resource_id")
            if local_id and stored_resource_id:
                local_to_real[int(local_id)] = int(stored_resource_id)
                continue
            data_b64 = res.get("_bytes_b64", "")
            if not local_id or not data_b64:
                continue
            try:
                import base64
                data = base64.b64decode(data_b64)
                real_res = await resource_svc.create_resource(
                    db, data,
                    owner_id=pkg.owner_id,
                    resource_type=res.get("type", "image"),
                    mime_type=res.get("mime_type", "application/octet-stream"),
                    filename=res.get("filename", "resource.bin"),
                    description=res.get("description"),
                )
                local_to_real[int(local_id)] = real_res["id"]
            except Exception as e:
                logger.warning("Failed to save resource %s: %s", local_id, e)

        # Update blocks with real resource IDs
        for block in _iter_all_blocks(raw_blocks):
            ref = block.get("resource_ref")
            if ref is not None and int(ref) in local_to_real:
                block["resource_ref"] = local_to_real[int(ref)]

        manifest_dict = {
            "title": file_record.name or "",
            "source_file_id": pkg.source_file_id,
            "extension": ext,
            "package_type": pkg.package_type,
            "created_by_parser": f"{module_key}:{action}",
            "parser_version": "1.0",
            "source_hash": file_record.md5_hash or "",
        }

        parse_status = _compute_package_parse_status(resource_diagnostics)

        content_ir = {
            "manifest": manifest_dict,
            "blocks": raw_blocks,
        }
        if isinstance(resource_diagnostics, list) and resource_diagnostics:
            content_ir["resource_diagnostics"] = resource_diagnostics
        content_ir["parse_status"] = parse_status

        content_json_str = json.dumps(content_ir, ensure_ascii=False)

        source_bytes_str = file_record.md5_hash or ""
        pkg.source_hash = hashlib.sha256(source_bytes_str.encode()).hexdigest()
        pkg.manifest_json = json.dumps(manifest_dict, ensure_ascii=False)
        pkg.status = parse_status
        pkg.parse_error = None

        version_no = 1
        if pkg.current_version_id:
            current_ver = await db.get(ContentPackageVersion, pkg.current_version_id)
            if current_ver:
                version_no = current_ver.version_no + 1
        else:
            existing = await db.execute(
                select(ContentPackageVersion).where(
                    ContentPackageVersion.package_id == pkg.id,
                ).order_by(ContentPackageVersion.version_no.desc()).limit(1)
            )
            existing_ver = existing.scalar_one_or_none()
            if existing_ver:
                version_no = existing_ver.version_no + 1

        version = ContentPackageVersion(
            package_id=pkg.id,
            version_no=version_no,
            content_json=content_json_str,
            summary=f"Parsed via {module_key}:{action}",
            operation_type="parse",
            created_by=pkg.owner_id,
        )
        db.add(version)
        await db.flush()
        pkg.current_version_id = version.id

        # Create resource refs for the saved resources
        for local_id, real_id in local_to_real.items():
            try:
                await resource_svc.add_ref(
                    db, pkg.id, real_id,
                    block_id=None,
                    version_id=version.id,
                )
            except Exception as e:
                logger.warning("Failed to add resource ref for resource_id=%s: %s", real_id, e)

        await db.commit()
        await db.refresh(pkg)

        return self._package_to_dict(pkg)

    async def get_package(
        self, db: AsyncSession, package_id: int | None = None,
        file_id: int | None = None, owner_id: int | None = None,
    ) -> dict[str, Any]:
        pkg = None
        if package_id:
            pkg = await db.get(ContentPackage, package_id)
        elif file_id:
            pkg = await self._find_active_by_file(db, file_id)

        if not pkg or pkg.deleted:
            raise NotFound("ContentPackage not found")
        if owner_id is not None and pkg.owner_id != owner_id:
            if pkg.source_file_id:
                await check_file_access(db, pkg.source_file_id, owner_id)
            else:
                raise PermissionDenied("Permission denied")
        return self._package_to_dict(pkg)

    async def get_full_package(
        self, db: AsyncSession, package_id: int, owner_id: int | None = None,
    ) -> dict[str, Any]:
        pkg = await self.get_package(db, package_id=package_id, owner_id=owner_id)
        version = await self._get_current_version(db, package_id)
        content_ir = json.loads(version.content_json) if version and version.content_json else {"manifest": {}, "blocks": []}

        refs_result = await db.execute(
            select(ResourceRef).where(ResourceRef.package_id == package_id)
        )
        refs = [self._ref_to_dict(r) for r in refs_result.scalars().all()]

        return {
            "package": pkg,
            "version": self._version_to_dict(version) if version else None,
            "content": content_ir,
            "resource_refs": refs,
        }

    async def list_blocks(
        self, db: AsyncSession, package_id: int,
        block_type: str | None = None, page: int | None = None,
        owner_id: int | None = None,
    ) -> list[dict]:
        await self.get_package(db, package_id=package_id, owner_id=owner_id)
        version = await self._get_current_version(db, package_id)
        if not version:
            return []

        content_ir = json.loads(version.content_json) if version.content_json else {}
        blocks = content_ir.get("blocks", [])

        result = []
        self._flatten_blocks(blocks, result, block_type=block_type, page=page)
        return result

    async def get_block(
        self, db: AsyncSession, package_id: int, block_id: str,
        owner_id: int | None = None,
    ) -> dict:
        blocks = await self.list_blocks(db, package_id, owner_id=owner_id)
        for b in blocks:
            if b.get("id") == block_id:
                return b
        raise NotFound(f"Block {block_id} not found in package {package_id}")

    async def update_blocks(
        self, db: AsyncSession, package_id: int,
        updates: list[BlockUpdateRequest], caller: str,
        owner_id: int | None = None,
        expected_version_id: int | None = None,
    ) -> dict[str, Any]:
        pkg = await self.get_package(db, package_id=package_id, owner_id=owner_id)
        version = await self._get_current_version(db, package_id)
        if not version:
            raise ValidationError("No version to update")

        if expected_version_id is not None and version.id != expected_version_id:
            raise ConflictError(
                f"Version conflict: expected {expected_version_id}, "
                f"current is {version.id}"
            )

        content_ir = json.loads(version.content_json) if version.content_json else {"manifest": {}, "blocks": []}
        update_map = {u.block_id: u for u in updates}

        def _apply(blocks: list[dict]) -> bool:
            changed = False
            for b in blocks:
                if b.get("id") in update_map:
                    u = update_map[b["id"]]
                    if u.text is not None:
                        b["text"] = u.text
                        changed = True
                    if u.data is not None:
                        b["data"] = u.data
                        changed = True
                    if u.style is not None:
                        b["style"] = u.style
                        changed = True
                if b.get("children"):
                    if _apply(b["children"]):
                        changed = True
            return changed

        _apply(content_ir.get("blocks", []))

        new_version = ContentPackageVersion(
            package_id=package_id,
            version_no=(version.version_no or 0) + 1,
            content_json=json.dumps(content_ir, ensure_ascii=False),
            summary=f"Updated {len(updates)} block(s)",
            operation_type="update",
            created_by=pkg["owner_id"],
        )
        db.add(new_version)
        await db.flush()
        pkg_obj = await db.get(ContentPackage, package_id)
        if pkg_obj:
            pkg_obj.current_version_id = new_version.id
        await db.commit()

        return {"package_id": package_id, "version_id": new_version.id, "version_no": new_version.version_no}

    async def replace_text(
        self, db: AsyncSession, package_id: int,
        request: ReplaceTextRequest, caller: str,
        owner_id: int | None = None,
        expected_version_id: int | None = None,
    ) -> dict[str, Any]:
        pkg = await self.get_package(db, package_id=package_id, owner_id=owner_id)
        version = await self._get_current_version(db, package_id)
        if not version:
            raise ValidationError("No version to update")

        if expected_version_id is not None and version.id != expected_version_id:
            raise ConflictError(
                f"Version conflict: expected {expected_version_id}, "
                f"current is {version.id}"
            )

        content_ir = json.loads(version.content_json) if version.content_json else {"manifest": {}, "blocks": []}
        replacement_count = 0

        def _replace(blocks: list[dict]):
            nonlocal replacement_count
            for b in blocks:
                if request.old_text in b.get("text", ""):
                    if request.scope == "all":
                        b["text"] = b["text"].replace(request.old_text, request.new_text)
                    else:
                        b["text"] = b["text"].replace(request.old_text, request.new_text, 1)
                    replacement_count += 1
                if b.get("children"):
                    _replace(b["children"])

        _replace(content_ir.get("blocks", []))

        new_version = ContentPackageVersion(
            package_id=package_id,
            version_no=(version.version_no or 0) + 1,
            content_json=json.dumps(content_ir, ensure_ascii=False),
            summary=f"Replaced text '{request.old_text[:30]}' x{replacement_count}",
            operation_type="replace_text",
            created_by=pkg["owner_id"],
        )
        db.add(new_version)
        await db.flush()
        pkg_obj = await db.get(ContentPackage, package_id)
        if pkg_obj:
            pkg_obj.current_version_id = new_version.id
        await db.commit()

        return {"package_id": package_id, "version_id": new_version.id, "version_no": new_version.version_no, "replacement_count": replacement_count}

    async def append_blocks(
        self, db: AsyncSession, package_id: int,
        blocks: list[BlockAppendRequest], caller: str,
        owner_id: int | None = None,
        expected_version_id: int | None = None,
    ) -> dict[str, Any]:
        pkg = await self.get_package(db, package_id=package_id, owner_id=owner_id)
        version = await self._get_current_version(db, package_id)
        if not version:
            raise ValidationError("No version to update")

        if expected_version_id is not None and version.id != expected_version_id:
            raise ConflictError(
                f"Version conflict: expected {expected_version_id}, "
                f"current is {version.id}"
            )

        content_ir = json.loads(version.content_json) if version.content_json else {"manifest": {}, "blocks": []}

        new_blocks = []
        for b in blocks:
            block_dict = {
                "id": f"b{hashlib.md5(f'{datetime.now().timestamp()}:{b.type}:{b.text}'.encode()).hexdigest()[:12]}",
                "type": b.type,
                "text": b.text,
                "data": b.data,
                "style": b.style,
                "children": [],
            }
            new_blocks.append(block_dict)

        if blocks[0].parent_id:
            def _find_and_append(parent_list: list[dict]):
                for item in parent_list:
                    if item.get("id") == blocks[0].parent_id:
                        item.setdefault("children", []).extend(new_blocks)
                        return True
                    if item.get("children"):
                        if _find_and_append(item["children"]):
                            return True
                return False
            _find_and_append(content_ir.get("blocks", []))
        else:
            content_ir.setdefault("blocks", []).extend(new_blocks)

        new_version = ContentPackageVersion(
            package_id=package_id,
            version_no=(version.version_no or 0) + 1,
            content_json=json.dumps(content_ir, ensure_ascii=False),
            summary=f"Appended {len(new_blocks)} block(s)",
            operation_type="append",
            created_by=pkg["owner_id"],
        )
        db.add(new_version)
        await db.flush()
        pkg_obj = await db.get(ContentPackage, package_id)
        if pkg_obj:
            pkg_obj.current_version_id = new_version.id
        await db.commit()

        return {"package_id": package_id, "version_id": new_version.id, "version_no": new_version.version_no, "blocks_added": len(new_blocks)}

    async def list_versions(
        self, db: AsyncSession, package_id: int,
        owner_id: int | None = None,
    ) -> list[dict]:
        await self.get_package(db, package_id=package_id, owner_id=owner_id)
        result = await db.execute(
            select(ContentPackageVersion)
            .where(ContentPackageVersion.package_id == package_id)
            .order_by(ContentPackageVersion.version_no.desc())
        )
        return [self._version_to_dict(v) for v in result.scalars().all()]

    async def restore_version(
        self, db: AsyncSession, package_id: int, version_id: int,
        caller: str, owner_id: int | None = None,
    ) -> dict[str, Any]:
        pkg = await self.get_package(db, package_id=package_id, owner_id=owner_id)
        old_version = await db.get(ContentPackageVersion, version_id)
        if not old_version or old_version.package_id != package_id:
            raise NotFound(f"Version {version_id} not found in package {package_id}")

        current = await self._get_current_version(db, package_id)

        new_version = ContentPackageVersion(
            package_id=package_id,
            version_no=(current.version_no if current else 0) + 1,
            content_json=old_version.content_json,
            summary=f"Restored from version {old_version.version_no}",
            operation_type="restore",
            created_by=pkg["owner_id"],
        )
        db.add(new_version)
        await db.flush()
        pkg_obj = await db.get(ContentPackage, package_id)
        if pkg_obj:
            pkg_obj.current_version_id = new_version.id
        await db.commit()

        return {"package_id": package_id, "version_id": new_version.id, "version_no": new_version.version_no}

    async def list_resources(
        self, db: AsyncSession, package_id: int,
        owner_id: int | None = None,
    ) -> list[dict]:
        await self.get_package(db, package_id=package_id, owner_id=owner_id)
        result = await db.execute(
            select(ResourceRef).where(ResourceRef.package_id == package_id)
        )
        refs = result.scalars().all()

        resource_ids = [r.resource_id for r in refs]
        if not resource_ids:
            return []

        resources = await db.execute(
            select(Resource).where(Resource.id.in_(resource_ids))
        )
        return [self._resource_to_dict(r) for r in resources.scalars().all()]

    async def get_resource(
        self, db: AsyncSession, resource_id: int,
        owner_id: int | None = None,
    ) -> dict:
        resource = await db.get(Resource, resource_id)
        if not resource:
            raise NotFound(f"Resource {resource_id} not found")
        if owner_id is not None and resource.owner_id != owner_id:
            # Check all package refs; a globally deduplicated resource can be
            # referenced from multiple packages owned/shared by different users.
            ref_result = await db.execute(
                select(ResourceRef).where(ResourceRef.resource_id == resource_id)
            )
            for ref in ref_result.scalars().all():
                pkg = await db.get(ContentPackage, ref.package_id)
                if not pkg or pkg.deleted:
                    continue
                if pkg.owner_id == owner_id:
                    return self._resource_to_dict(resource)
                if pkg.source_file_id:
                    try:
                        await check_file_access(db, pkg.source_file_id, owner_id)
                        return self._resource_to_dict(resource)
                    except (NotFound, PermissionDenied):
                        continue
            raise PermissionDenied("Permission denied")
        return self._resource_to_dict(resource)

    async def delete_package(
        self, db: AsyncSession, package_id: int, owner_id: int | None = None,
    ) -> dict:
        pkg = await db.get(ContentPackage, package_id)
        if not pkg or pkg.deleted:
            raise NotFound("ContentPackage not found")
        if owner_id is not None and pkg.owner_id != owner_id:
            raise PermissionDenied("Permission denied")

        pkg.deleted = True
        pkg.deleted_at = datetime.now(timezone.utc)
        pkg.status = "stale"
        await db.commit()
        return {"deleted": True}

    async def _find_active_by_file(self, db: AsyncSession, file_id: int) -> ContentPackage | None:
        result = await db.execute(
            select(ContentPackage).where(
                ContentPackage.source_file_id == file_id,
                ContentPackage.deleted.is_(False),
            ).order_by(ContentPackage.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_current_version(self, db: AsyncSession, package_id: int) -> ContentPackageVersion | None:
        pkg = await db.get(ContentPackage, package_id)
        if not pkg:
            return None
        if pkg.current_version_id:
            return await db.get(ContentPackageVersion, pkg.current_version_id)
        result = await db.execute(
            select(ContentPackageVersion)
            .where(ContentPackageVersion.package_id == package_id)
            .order_by(ContentPackageVersion.version_no.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _flatten_blocks(
        self, blocks: list[dict], result: list[dict],
        block_type: str | None = None, page: int | None = None,
    ):
        for b in blocks:
            if block_type and b.get("type") != block_type:
                pass
            elif page is not None and b.get("page") != page:
                pass
            else:
                result.append(b)
            if b.get("children"):
                self._flatten_blocks(b["children"], result, block_type, page)

    def _package_to_dict(self, pkg: ContentPackage) -> dict:
        manifest = None
        if pkg.manifest_json:
            try:
                manifest = json.loads(pkg.manifest_json)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": pkg.id,
            "owner_id": pkg.owner_id,
            "source_file_id": pkg.source_file_id,
            "package_type": pkg.package_type,
            "source_extension": pkg.source_extension,
            "origin_type": pkg.origin_type if hasattr(pkg, "origin_type") else "uploaded",
            "package_version": pkg.package_version,
            "manifest": manifest,
            "current_version_id": pkg.current_version_id,
            "status": pkg.status,
            "parse_error": pkg.parse_error,
            "source_hash": pkg.source_hash,
            "created_at": pkg.created_at.isoformat() if pkg.created_at else None,
            "updated_at": pkg.updated_at.isoformat() if pkg.updated_at else None,
        }

    def _version_to_dict(self, v: ContentPackageVersion) -> dict:
        return {
            "id": v.id,
            "package_id": v.package_id,
            "version_no": v.version_no,
            "content_json": v.content_json,
            "summary": v.summary,
            "operation_type": v.operation_type,
            "operation_meta_json": v.operation_meta_json,
            "created_by": v.created_by,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }

    def _resource_to_dict(self, r: Resource) -> dict:
        vlm = r.vlm_metadata
        if isinstance(vlm, str):
            try:
                vlm = json.loads(vlm)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": r.id,
            "owner_id": r.owner_id,
            "hash": r.hash,
            "hash_algorithm": r.hash_algorithm,
            "resource_type": r.resource_type,
            "mime_type": r.mime_type,
            "storage_path": r.storage_path,
            "file_size": r.file_size,
            "width": r.width,
            "height": r.height,
            "duration_ms": r.duration_ms,
            "description": r.description,
            "ocr_text": r.ocr_text,
            "vlm_metadata": vlm,
            "ref_count": r.ref_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    def _ref_to_dict(self, ref: ResourceRef) -> dict:
        coords = ref.coordinates
        if isinstance(coords, str):
            try:
                coords = json.loads(coords)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": ref.id,
            "package_id": ref.package_id,
            "version_id": ref.version_id,
            "resource_id": ref.resource_id,
            "block_id": ref.block_id,
            "usage_type": ref.usage_type,
            "page": ref.page,
            "coordinates": coords,
            "usage_hints": ref.usage_hints,
        }
