"""Content Package REST endpoints."""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.content_package import (
    BlockAppendRequest,
    BlockUpdateRequest,
    ExportRequest,
    PublishRequest,
    ReplaceTextRequest,
)
from app.services.content.export_service import ContentExportService
from app.services.content.package_lifecycle_service import (
    archive_lifecycle_unavailable_packages,
    audit_content_package_lifecycle_debt,
    handle_file_deleted,
    handle_file_permanently_deleted,
    handle_file_restored,
    repair_missing_current_versions,
)
from app.services.content.package_service import ContentPackageService, is_package_consumable_status
from app.services.content.pipeline_service import ContentPipelineService
from app.services.content.resource_service import ResourceService
from app.services.file_reader import resolve_caller_user_id
from app.services.module_registry import register_capability

logger = logging.getLogger("v2.content")

router = APIRouter(prefix="/api/content", tags=["content"])

pkg_svc = ContentPackageService()
pipeline_svc = ContentPipelineService()
export_svc = ContentExportService()
resource_svc = ResourceService()


def _pipeline_failure(result: object) -> str | None:
    if not isinstance(result, dict):
        return None
    if result.get("success") is False:
        return str(result.get("error") or "Content pipeline returned success=false")
    status = str(result.get("status") or "").lower()
    if status in {"failed", "error"}:
        return str(result.get("error") or f"Content pipeline returned status={status}")
    if "error" in result and result.get("success") is not True:
        return str(result.get("error") or "Content pipeline returned error")
    data = result.get("data")
    if isinstance(data, dict):
        return _pipeline_failure(data)
    return None


# ── Schemas ──────────────────────────────────────────────────────

class PipelineRequest(BaseModel):
    file_id: int


class PackageQuery(BaseModel):
    package_id: int | None = None
    file_id: int | None = None


class UpdateBlocksRequest(BaseModel):
    package_id: int
    updates: list[BlockUpdateRequest]
    expected_version_id: int | None = None


class AppendBlocksRequest(BaseModel):
    package_id: int
    blocks: list[BlockAppendRequest]
    expected_version_id: int | None = None


class ReplaceTextBody(BaseModel):
    package_id: int
    request: ReplaceTextRequest
    expected_version_id: int | None = None


class VersionRestoreRequest(BaseModel):
    package_id: int
    version_id: int


# ── REST Endpoints ───────────────────────────────────────────────

@router.post("/pipeline")
async def trigger_pipeline(
    body: PipelineRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    caller = f"user:{user.id}"
    result = await pipeline_svc.run_pipeline(body.file_id, caller)
    pipeline_error = _pipeline_failure(result)
    if pipeline_error:
        from app.core.exceptions import AppException
        raise AppException(f"Pipeline failed: {pipeline_error}", status_code=422)
    return ApiResponse(data=result)


@router.get("/packages")
async def list_packages(
    file_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    if file_id:
        pkg = await pkg_svc.get_package(db, file_id=file_id, owner_id=user.id)
        return ApiResponse(data=pkg)
    return ApiResponse(data={"packages": []})


@router.get("/packages/{package_id}")
async def get_package(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await pkg_svc.get_package(db, package_id=package_id, owner_id=user.id)
    return ApiResponse(data=result)


@router.get("/packages/{package_id}/full")
async def get_full_package(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await pkg_svc.get_full_package(db, package_id=package_id, owner_id=user.id)
    return ApiResponse(data=result)


@router.get("/packages/{package_id}/blocks")
async def list_blocks(
    package_id: int,
    block_type: str | None = None,
    page: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await pkg_svc.list_blocks(
        db, package_id, block_type=block_type, page=page, owner_id=user.id,
    )
    return ApiResponse(data={"blocks": result})


@router.get("/packages/{package_id}/blocks/{block_id}")
async def get_block(
    package_id: int, block_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await pkg_svc.get_block(db, package_id, block_id, owner_id=user.id)
    return ApiResponse(data=result)


@router.put("/packages/{package_id}/blocks")
async def update_blocks(
    package_id: int,
    body: UpdateBlocksRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    caller = f"user:{user.id}"
    result = await pkg_svc.update_blocks(
        db, package_id, body.updates, caller,
        owner_id=user.id, expected_version_id=body.expected_version_id,
    )
    return ApiResponse(data=result)


@router.post("/packages/{package_id}/blocks")
async def append_blocks(
    package_id: int,
    body: AppendBlocksRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    caller = f"user:{user.id}"
    result = await pkg_svc.append_blocks(
        db, package_id, body.blocks, caller,
        owner_id=user.id, expected_version_id=body.expected_version_id,
    )
    return ApiResponse(data=result)


@router.post("/packages/{package_id}/replace-text")
async def replace_text(
    package_id: int,
    body: ReplaceTextBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    caller = f"user:{user.id}"
    result = await pkg_svc.replace_text(
        db, package_id, body.request, caller,
        owner_id=user.id, expected_version_id=body.expected_version_id,
    )
    return ApiResponse(data=result)


@router.get("/packages/{package_id}/versions")
async def list_versions(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await pkg_svc.list_versions(db, package_id, owner_id=user.id)
    return ApiResponse(data={"versions": result})


@router.post("/packages/{package_id}/restore")
async def restore_version(
    package_id: int,
    body: VersionRestoreRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    caller = f"user:{user.id}"
    result = await pkg_svc.restore_version(db, package_id, body.version_id, caller, owner_id=user.id)
    return ApiResponse(data=result)


@router.get("/packages/{package_id}/resources")
async def list_resources(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await pkg_svc.list_resources(db, package_id, owner_id=user.id)
    return ApiResponse(data={"resources": result})


@router.get("/resources/{resource_id}")
async def get_resource(
    resource_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await pkg_svc.get_resource(db, resource_id, owner_id=user.id)
    return ApiResponse(data=result)


@router.post("/packages/{package_id}/export")
async def export_package(
    package_id: int,
    body: ExportRequest = ExportRequest(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await export_svc.export(
        db, package_id,
        target_format=body.target_format,
        owner_id=user.id,
        conflict_policy=body.conflict_policy,
    )
    return ApiResponse(data=result)


@router.post("/packages/{package_id}/publish")
async def publish_package(
    package_id: int,
    body: PublishRequest = PublishRequest(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await export_svc.publish(
        db, package_id,
        target_file_id=body.target_file_id,
        owner_id=user.id,
        conflict_policy=body.conflict_policy,
    )
    return ApiResponse(data=result)


@router.delete("/packages/{package_id}")
async def delete_package(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    result = await pkg_svc.delete_package(db, package_id, owner_id=user.id)
    return ApiResponse(data=result)


# ── Capability handlers ──────────────────────────────────────────

async def _cap_pipeline(params: dict, caller: str) -> dict:
    file_id = params.get("file_id")
    if not file_id:
        return {"success": False, "error": "file_id required"}
    try:
        result = await pipeline_svc.run_pipeline(file_id, caller)
        pipeline_error = _pipeline_failure(result)
        if pipeline_error:
            return {"success": False, "error": pipeline_error, "data": result}
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _cap_get_package(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    file_id = params.get("file_id")
    if not package_id and not file_id:
        return {"success": False, "error": "package_id or file_id required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.get_package(db, package_id=package_id, file_id=file_id, owner_id=owner_id)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_get_file_content(params: dict, caller: str) -> dict:
    """Get the best available content for a file: ContentPackage → parse fallback.

    Returns structured blocks for viewer rendering, or triggers a lazy parse.
    """
    file_id = params.get("file_id")
    if not file_id:
        return {"success": False, "error": "file_id required"}
    owner_id = resolve_caller_user_id(caller)

    def fail_content(error: str, status: str, source: str = "none", package_id: int | None = None) -> dict:
        data = {"source": source, "status": status, "download_url": f"/api/files/download/{file_id}/original"}
        if package_id is not None:
            data["package_id"] = package_id
        return {"success": False, "error": error, "data": data}

    def blocks_from_full_package(full: dict) -> list:
        content = full.get("content", {})
        blocks = content.get("blocks", [])
        if full.get("version") and full["version"].get("content_json"):
            import json
            parsed = json.loads(full["version"]["content_json"])
            blocks = parsed.get("blocks", blocks)
        return blocks

    async with AsyncSessionLocal() as db:
        try:
            from app.core.exceptions import NotFound as AppNotFound
            from app.services.content.package_service import ContentPackageService
            from app.services.file_service import check_file_access as file_access
            from app.services.file_service import get_file_record
            file_record = await get_file_record(db, file_id)
            if not file_record:
                return {"success": False, "error": "File not found"}

            await file_access(db, file_id, owner_id)
            pkg_svc = ContentPackageService()
            try:
                pkg = await pkg_svc.get_package(db, file_id=file_id, owner_id=owner_id)
            except AppNotFound:
                pkg = None
            if pkg and is_package_consumable_status(pkg.get("status")):
                full = await pkg_svc.get_full_package(db, pkg["id"], owner_id=owner_id)
                blocks = blocks_from_full_package(full)
                if not blocks:
                    return fail_content(
                        "Content package contains no consumable blocks",
                        str(pkg.get("status") or "empty_blocks"),
                        source="content_package",
                        package_id=pkg["id"],
                    )
                return {"success": True, "data": {
                    "source": "content_package",
                    "package_id": pkg["id"],
                    "blocks": blocks,
                    "manifest": pkg.get("manifest"),
                    "status": pkg.get("status"),
                }}

            # No parsed package → trigger lazy pipeline
            from app.services.content.pipeline_service import ContentPipelineService
            pipeline_svc = ContentPipelineService()
            try:
                pipeline_result = await pipeline_svc.run_pipeline(file_id, caller)
            except Exception as e:
                return fail_content(str(e), "parse_failed")

            pipeline_error = _pipeline_failure(pipeline_result)
            if pipeline_error:
                return fail_content(pipeline_error, "parse_failed")

            if isinstance(pipeline_result, dict) and pipeline_result.get("skipped"):
                return fail_content(str(pipeline_result.get("reason") or "Content pipeline skipped"), "skipped")

            if pipeline_result:
                try:
                    pkg = await pkg_svc.get_package(db, file_id=file_id, owner_id=owner_id)
                except AppNotFound:
                    pkg = None
                if pkg and is_package_consumable_status(pkg.get("status")):
                    full = await pkg_svc.get_full_package(db, pkg["id"], owner_id=owner_id)
                    blocks = blocks_from_full_package(full)
                    if not blocks:
                        return fail_content(
                            "Content package contains no consumable blocks",
                            str(pkg.get("status") or "empty_blocks"),
                            source="content_package",
                            package_id=pkg["id"],
                        )
                    return {"success": True, "data": {
                        "source": "content_package",
                        "package_id": pkg["id"],
                        "blocks": blocks,
                        "status": pkg.get("status"),
                    }}
                if pkg:
                    return fail_content(
                        f"Content package is not consumable: {pkg.get('status')}",
                        str(pkg.get("status") or "not_parsed"),
                        source="content_package",
                        package_id=pkg["id"],
                    )

            return fail_content("No consumable content package available", "not_parsed")
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_get_full(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    if not package_id:
        return {"success": False, "error": "package_id required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.get_full_package(db, package_id, owner_id=owner_id)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_list_blocks(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    block_type = params.get("block_type")
    page = params.get("page")
    if not package_id:
        return {"success": False, "error": "package_id required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.list_blocks(db, package_id, block_type=block_type, page=page, owner_id=owner_id)
            return {"success": True, "data": {"blocks": result}}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_get_block(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    block_id = params.get("block_id")
    if not package_id or not block_id:
        return {"success": False, "error": "package_id and block_id required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.get_block(db, package_id, block_id, owner_id=owner_id)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_update_blocks(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    updates_data = params.get("updates", [])
    if not package_id or not updates_data:
        return {"success": False, "error": "package_id and updates required"}
    owner_id = resolve_caller_user_id(caller)
    expected_version_id = params.get("expected_version_id")
    updates = [BlockUpdateRequest(**u) for u in updates_data]
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.update_blocks(
                db, package_id, updates, caller,
                owner_id=owner_id, expected_version_id=expected_version_id,
            )
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_append_blocks(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    blocks_data = params.get("blocks", [])
    if not package_id or not blocks_data:
        return {"success": False, "error": "package_id and blocks required"}
    owner_id = resolve_caller_user_id(caller)
    expected_version_id = params.get("expected_version_id")
    blocks = [BlockAppendRequest(**b) for b in blocks_data]
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.append_blocks(
                db, package_id, blocks, caller,
                owner_id=owner_id, expected_version_id=expected_version_id,
            )
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_replace_text(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    req_data = params.get("request", {})
    if not package_id or not req_data:
        return {"success": False, "error": "package_id and request required"}
    owner_id = resolve_caller_user_id(caller)
    expected_version_id = params.get("expected_version_id")
    req = ReplaceTextRequest(**req_data)
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.replace_text(
                db, package_id, req, caller,
                owner_id=owner_id, expected_version_id=expected_version_id,
            )
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_export(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    target_format = params.get("target_format")
    conflict_policy = params.get("conflict_policy", "auto_rename")
    if not package_id:
        return {"success": False, "error": "package_id required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            result = await export_svc.export(
                db,
                package_id,
                target_format=target_format,
                owner_id=owner_id,
                conflict_policy=conflict_policy,
            )
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_publish(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    target_file_id = params.get("target_file_id")
    conflict_policy = params.get("conflict_policy", "create_version")
    if not package_id:
        return {"success": False, "error": "package_id required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            result = await export_svc.publish(
                db,
                package_id,
                target_file_id=target_file_id,
                owner_id=owner_id,
                conflict_policy=conflict_policy,
            )
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_list_versions(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    if not package_id:
        return {"success": False, "error": "package_id required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.list_versions(db, package_id, owner_id=owner_id)
            return {"success": True, "data": {"versions": result}}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_restore_version(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    version_id = params.get("version_id")
    if not package_id or not version_id:
        return {"success": False, "error": "package_id and version_id required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.restore_version(db, package_id, version_id, caller, owner_id=owner_id)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_list_resources(params: dict, caller: str) -> dict:
    package_id = params.get("package_id")
    if not package_id:
        return {"success": False, "error": "package_id required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.list_resources(db, package_id, owner_id=owner_id)
            return {"success": True, "data": {"resources": result}}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_get_resource(params: dict, caller: str) -> dict:
    resource_id = params.get("resource_id")
    if not resource_id:
        return {"success": False, "error": "resource_id required"}
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            result = await pkg_svc.get_resource(db, resource_id, owner_id=owner_id)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_store_resource(params: dict, caller: str) -> dict:
    """Store an extracted embedded resource (image/attachment) from a parser module.

    Parser modules call this capability after extracting binary data from Office/PDF files.
    The resource is stored content-addressed, deduplicated by sha256.
    """
    data_b64 = params.get("data_b64")
    if not data_b64:
        return {"success": False, "error": "data_b64 required"}
    import base64
    data = base64.b64decode(data_b64, validate=True)
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            file_id = params.get("file_id")
            package_id = params.get("package_id")
            pkg_info_for_ref = None
            if file_id:
                from app.services.content.package_service import ContentPackageService
                from app.services.file_service import check_file_access
                await check_file_access(db, file_id, owner_id)
                pkg_svc_local = ContentPackageService()
                try:
                    pkg_info_for_ref = await pkg_svc_local.get_package(db, file_id=file_id, owner_id=owner_id)
                except Exception:
                    pkg_info_for_ref = None
            elif package_id:
                from app.services.content.package_service import ContentPackageService
                pkg_svc_local = ContentPackageService()
                pkg_info_for_ref = await pkg_svc_local.get_package(db, package_id=package_id, owner_id=owner_id)

            result = await resource_svc.create_resource(
                db, data,
                owner_id=owner_id,
                resource_type=params.get("resource_type", "image"),
                mime_type=params.get("mime_type", "application/octet-stream"),
                filename=params.get("filename", "resource.bin"),
                width=params.get("width"),
                height=params.get("height"),
                description=params.get("description"),
                ocr_text=params.get("ocr_text"),
            )
            # Update VLM metadata if provided
            if params.get("vlm_metadata"):
                await resource_svc.update_description(
                    db, result["id"],
                    vlm_metadata=params["vlm_metadata"],
                )
            if pkg_info_for_ref and pkg_info_for_ref.get("id"):
                await resource_svc.add_ref(
                    db, pkg_info_for_ref["id"], result["id"],
                    block_id=params.get("block_id"),
                    usage_hints=params.get("description", ""),
                )
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ── Content IR capabilities ──────────────────────────────────────


async def _cap_validate_ir(params: dict, caller: str) -> dict:
    from app.services.content.ir_validator import validate_ir
    content_ir = params.get("content_ir")
    if not content_ir:
        return {"success": False, "error": "content_ir required"}
    try:
        result = await validate_ir(content_ir)
        return {
            "success": True,
            "data": {
                "valid": result.valid,
                "errors": [e.model_dump() for e in result.errors],
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _cap_normalize_ir(params: dict, caller: str) -> dict:
    from app.services.content.ir_normalizer import normalize_ir
    from app.services.content.ir_validator import validate_ir
    content_ir = params.get("content_ir")
    if not content_ir:
        return {"success": False, "error": "content_ir required"}
    try:
        validation = await validate_ir(content_ir)
        if not validation.valid:
            return {
                "success": True,
                "data": {
                    "valid": False,
                    "errors": [e.model_dump() for e in validation.errors],
                },
            }
        normalized = await normalize_ir(content_ir)
        return {
            "success": True,
            "data": {
                "valid": True,
                "normalized_preview": normalized,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _cap_write_ir(params: dict, caller: str) -> dict:
    from app.core.exceptions import ValidationError as AppValidationError
    from app.services.content.ir_validator import validate_ir
    from app.services.content.ir_writer import write_ir
    content_ir = params.get("content_ir")
    if not content_ir:
        return {"success": False, "error": "content_ir required"}
    # Pre-validate with structured error response
    validation = await validate_ir(content_ir)
    if not validation.valid:
        return {
            "success": False,
            "error": "CONTENT_IR_VALIDATION_FAILED",
            "data": {
                "valid": False,
                "errors": [e.model_dump() for e in validation.errors],
            },
        }
    owner_id = resolve_caller_user_id(caller)
    if owner_id == 0:
        return {"success": False, "error": "Write operations require a real user context (system principal not allowed)"}
    source_file_id = params.get("source_file_id") or params.get("file_id")
    expected_version_id = params.get("expected_version_id")
    async with AsyncSessionLocal() as db:
        try:
            result = await write_ir(
                db, content_ir, owner_id, caller,
                source_file_id=source_file_id,
                expected_version_id=expected_version_id,
            )
            return {"success": True, "data": result}
        except AppValidationError as e:
            details = getattr(e, "details", None) or []
            return {
                "success": False,
                "error": "CONTENT_IR_VALIDATION_FAILED",
                "data": {
                    "valid": False,
                    "errors": details,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _cap_compile(params: dict, caller: str) -> dict:
    """Compile a ContentPackage to a temporary physical file for download.

    Does NOT create framework_file_items.
    Returns temp file path; caller is responsible for cleanup via BackgroundTask.

    Security: validates that the returned file path is within allowed temp directories
    and that the filename contains no path separators.
    """
    import os
    import tempfile
    from pathlib import Path

    from app.config import get_settings
    from app.models.content import ContentPackage
    from app.services.content.export_service import ContentExportService
    owner_id = resolve_caller_user_id(caller)
    package_id = params.get("package_id")
    target_format = params.get("target_format")
    if not package_id:
        return {"success": False, "error": "package_id required"}
    async with AsyncSessionLocal() as db:
        try:
            # Verify access: file-level check for shared packages, owner check as fallback
            pkg = await db.get(ContentPackage, package_id)
            if not pkg or pkg.deleted:
                return {"success": False, "error": "Package not found"}
            if pkg.source_file_id:
                from app.services.file_service import check_file_access
                access = await check_file_access(db, pkg.source_file_id, owner_id)
                if not access:
                    return {"success": False, "error": "Permission denied"}
            elif pkg.owner_id != owner_id:
                return {"success": False, "error": "Permission denied"}

            export_svc = ContentExportService()
            full = await export_svc.package_svc.get_full_package(
                db, package_id,
            )
            content = full.get("content", {})
            pkg_info = full.get("package", {})
            fmt = (target_format or pkg_info.get("source_extension", "docx")).lower().strip(".")
            file_path, filename = await export_svc._compile_to_file(
                db, pkg_info, fmt, content, owner_id=owner_id,
            )
            # Security: validate the returned file path
            file_path_obj = Path(file_path) if not isinstance(file_path, Path) else file_path
            file_path_str = str(file_path_obj.resolve())
            settings = get_settings()
            upload_root = Path(settings.UPLOAD_DIR).resolve().parent
            allowed_roots = [
                (upload_root / ".tmp_exports").resolve(),
                (upload_root / ".tmp_downloads").resolve(),
                Path(tempfile.gettempdir()).resolve(),
            ]
            allowed = any(
                os.path.commonpath([str(root), file_path_str]) == str(root)
                for root in allowed_roots
            )
            if not allowed or not file_path_obj.exists() or not file_path_obj.is_file():
                return {"success": False, "error": "Invalid compile output path"}
            # Filename must not contain path separators
            if "/" in filename or "\\" in filename:
                return {"success": False, "error": "Invalid filename"}
            return {
                "success": True,
                "data": {
                    "file_path": file_path_str,
                    "filename": filename,
                    "package_id": package_id,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# ── Event handler: file.uploaded → content pipeline ─────────────

async def _on_file_uploaded(payload: dict, caller: str, caller_role: str) -> dict:
    file_id = payload.get("file_id")
    if not file_id:
        return {"success": False, "error": "file_id required"}
    try:
        result = await pipeline_svc.handle_file_uploaded(payload, caller, caller_role)
        pipeline_error = _pipeline_failure(result)
        if pipeline_error:
            return {"success": False, "error": pipeline_error, "data": result}
        return {"success": True, "data": result}
    except Exception as e:
        logger.warning("Content pipeline from file.uploaded failed: %s", e)
        return {"success": False, "error": str(e)}


async def _on_file_deleted(payload: dict, caller: str, caller_role: str) -> dict:
    file_id = int(payload.get("file_id", 0) or 0)
    if file_id <= 0:
        return {"success": False, "error": "file_id required"}
    async with AsyncSessionLocal() as db:
        return await handle_file_deleted(db, file_id)


async def _on_file_restored(payload: dict, caller: str, caller_role: str) -> dict:
    file_id = int(payload.get("file_id", 0) or 0)
    if file_id <= 0:
        return {"success": False, "error": "file_id required"}
    async with AsyncSessionLocal() as db:
        return await handle_file_restored(db, file_id)


async def _on_file_permanently_deleted(payload: dict, caller: str, caller_role: str) -> dict:
    file_id = int(payload.get("file_id", 0) or 0)
    if file_id <= 0:
        return {"success": False, "error": "file_id required"}
    async with AsyncSessionLocal() as db:
        return await handle_file_permanently_deleted(db, file_id)


async def _cap_audit_lifecycle_debt(params: dict, caller: str) -> dict:
    limit = int(params.get("limit", 20) or 20)
    limit = max(1, min(limit, 500))
    async with AsyncSessionLocal() as db:
        return await audit_content_package_lifecycle_debt(db, limit=limit)


async def _cap_archive_lifecycle_unavailable_packages(params: dict, caller: str) -> dict:
    async with AsyncSessionLocal() as db:
        return await archive_lifecycle_unavailable_packages(
            db,
            dry_run=bool(params.get("dry_run", True)),
            limit=int(params.get("limit", 100) or 100),
            reason=str(params.get("reason", "source_unavailable") or "source_unavailable"),
            confirm=str(params.get("confirm", "") or ""),
            audit_reason=str(params.get("audit_reason", "") or ""),
        )


async def _cap_repair_missing_current_versions(params: dict, caller: str) -> dict:
    async with AsyncSessionLocal() as db:
        return await repair_missing_current_versions(
            db,
            dry_run=bool(params.get("dry_run", True)),
            limit=int(params.get("limit", 100) or 100),
            confirm=str(params.get("confirm", "") or ""),
        )


async def _cap_store_analysis_resource(params: dict, caller: str) -> dict:
    """Store VLM/analysis result as a Resource (viewer-safe, requires file_id).

    Unlike store_resource which requires editor role, this capability allows
    viewer callers to store VLM metadata, provided they have access to the
    referenced file. The file_id is required for access validation.
    """
    from app.services.content.resource_service import ResourceService
    from app.services.file_service import check_file_access, get_file_record

    data_b64 = params.get("data_b64")
    file_id = params.get("file_id")
    if not data_b64:
        return {"success": False, "error": "data_b64 required"}
    if not file_id:
        return {"success": False, "error": "file_id required for access validation"}

    import base64
    data = base64.b64decode(data_b64, validate=True)
    owner_id = resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        try:
            file_rec = await get_file_record(db, file_id)
            if not file_rec:
                return {"success": False, "error": "File not found"}
            await check_file_access(db, file_id, owner_id)

            resource_svc = ResourceService()
            result = await resource_svc.create_resource(
                db, data,
                owner_id=owner_id,
                resource_type=params.get("resource_type", "image"),
                mime_type=params.get("mime_type", "application/octet-stream"),
                filename=params.get("filename", "resource.bin"),
                width=params.get("width"),
                height=params.get("height"),
                description=params.get("description"),
                ocr_text=params.get("ocr_text"),
            )
            if params.get("vlm_metadata"):
                await resource_svc.update_description(
                    db, result["id"],
                    vlm_metadata=params["vlm_metadata"],
                )
            # Create ResourceRef via package linked to file
            from app.services.content.package_service import ContentPackageService
            pkg_svc_local = ContentPackageService()
            pkg_info = await pkg_svc_local.get_package(db, file_id=file_id, owner_id=owner_id)
            if pkg_info and pkg_info.get("id"):
                await resource_svc.add_ref(
                    db, pkg_info["id"], result["id"],
                    block_id=params.get("block_id"),
                    usage_hints=params.get("description", ""),
                )
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


from app.services.module_events import register_module_event_handler

register_module_event_handler("file.uploaded", _on_file_uploaded, "content")
register_module_event_handler("file.deleted", _on_file_deleted, "content")
register_module_event_handler("file.restored", _on_file_restored, "content")
register_module_event_handler("file.permanent_deleted", _on_file_permanently_deleted, "content")
register_module_event_handler("file.permanently_deleted", _on_file_permanently_deleted, "content")

# ── Register capabilities ────────────────────────────────────────

def register_content_capabilities():
    # Read-only capabilities (viewer)
    _register_viewer_caps()
    # Viewer-safe resource store (for parser/VLM backfill with file access check)
    register_capability(
        "content", "store_analysis_resource", _cap_store_analysis_resource,
        description="Store VLM/analysis result as Resource (viewer-safe, requires file_id access check)",
        parameters={
            "data_b64": "string", "resource_type": "string", "mime_type": "string",
            "filename": "string", "description": "string (optional)", "ocr_text": "string (optional)",
            "vlm_metadata": "object (optional)", "file_id": "int (required)",
        },
        min_role="viewer",
    )
    register_capability(
        "content", "archive_lifecycle_unavailable_packages", _cap_archive_lifecycle_unavailable_packages,
        description="Dry-run or confirm archive ContentPackages whose source file is unavailable",
        parameters={
            "dry_run": "bool", "limit": "int",
            "reason": "source_unavailable|source_file_deleted|source_file_missing",
            "confirm": "ARCHIVE_LIFECYCLE_UNAVAILABLE_PACKAGES",
            "audit_reason": "str",
        },
        min_role="admin",
    )
    register_capability(
        "content", "repair_missing_current_versions", _cap_repair_missing_current_versions,
        description="Dry-run or confirm repair ContentPackages missing current_version_id when historical versions exist",
        parameters={"dry_run": "bool", "limit": "int", "confirm": "REPAIR_CONTENT_CURRENT_VERSION"},
        min_role="admin",
    )
    # Write capabilities (editor)
    _register_editor_caps()
    logger.info("Registered all content:* capabilities")


def _register_viewer_caps():
    viewer_caps = [
        ("get_package", _cap_get_package, "Get content package metadata", {"package_id": "int (optional)", "file_id": "int (optional)"}),
        ("get_full_package", _cap_get_full, "Get full content package with blocks and resource refs", {"package_id": "int"}),
        ("get_file_content", _cap_get_file_content, "Get file content from ContentPackage (lazy parse if needed)", {"file_id": "int"}),
        ("list_blocks", _cap_list_blocks, "List blocks in a content package", {"package_id": "int", "block_type": "str (optional)", "page": "int (optional)"}),
        ("get_block", _cap_get_block, "Get a single block by ID", {"package_id": "int", "block_id": "str"}),
        ("list_versions", _cap_list_versions, "List all versions of a content package", {"package_id": "int"}),
        ("list_resources", _cap_list_resources, "List resources referenced by a package", {"package_id": "int"}),
        ("get_resource", _cap_get_resource, "Get resource metadata by ID", {"resource_id": "int"}),
        ("audit_lifecycle_debt", _cap_audit_lifecycle_debt, "Audit ContentPackage source-file lifecycle debt", {"limit": "int (optional)"}),
        ("validate_ir", _cap_validate_ir, "Validate Content IR structure and semantics", {"content_ir": "object"}),
        ("normalize_ir", _cap_normalize_ir, "Normalize Content IR (fill defaults, ids)", {"content_ir": "object"}),
        ("compile", _cap_compile, "Compile ContentPackage to temporary physical file for download", {"package_id": "int", "target_format": "str (optional)"}),
    ]
    for action, handler, desc, params in viewer_caps:
        register_capability(
            "content", action, handler,
            description=desc,
            parameters=params,
            min_role="viewer",
        )


def _register_editor_caps():
    editor_caps = [
        ("pipeline", _cap_pipeline, "Automated content pipeline: parse file → content package", {"file_id": "int"}),
        ("update_blocks", _cap_update_blocks, "Update one or more blocks", {"package_id": "int", "updates": "list[{block_id, text?, data?, style?}]", "expected_version_id": "int (optional)"}),
        ("append_blocks", _cap_append_blocks, "Append new blocks to a package", {"package_id": "int", "blocks": "list[{type, text, data?, style?}]", "expected_version_id": "int (optional)"}),
        ("replace_text", _cap_replace_text, "Find and replace text across blocks", {"package_id": "int", "request": "{old_text, new_text, scope}", "expected_version_id": "int (optional)"}),
        ("export", _cap_export, "Export content package to a physical file", {"package_id": "int", "target_format": "str (optional)"}),
        ("publish", _cap_publish, "Publish content package as an artifact", {"package_id": "int", "target_file_id": "int (optional)", "conflict_policy": "str (optional)"}),
        ("restore_version", _cap_restore_version, "Restore a previous version", {"package_id": "int", "version_id": "int"}),
        ("store_resource", _cap_store_resource, "Store an extracted embedded resource (data_b64, mime_type, filename, description, ocr_text, vlm_metadata, file_id, package_id, block_id)", {"data_b64": "string", "resource_type": "string", "mime_type": "string", "filename": "string", "description": "string (optional)", "ocr_text": "string (optional)", "vlm_metadata": "object (optional)", "file_id": "int (optional)", "package_id": "int (optional)", "block_id": "string (optional)"}),
        ("write_ir", _cap_write_ir, "Write validated Content IR to canonical DB source", {"content_ir": "object", "file_id": "int (optional)", "source_file_id": "int (optional)", "expected_version_id": "int (optional)"}),
    ]
    for action, handler, desc, params in editor_caps:
        register_capability(
            "content", action, handler,
            description=desc,
            parameters=params,
            min_role="editor",
        )

    # Viewer-safe resource storage for parser/VLM backfill
    register_capability(
        "content", "store_analysis_resource", _cap_store_analysis_resource,
        description="Store VLM/analysis result as Resource (viewer-safe, requires file_id access check)",
        parameters={
            "data_b64": "string", "resource_type": "string", "mime_type": "string",
            "filename": "string", "description": "string (optional)", "ocr_text": "string (optional)",
            "vlm_metadata": "object (optional)", "file_id": "int (required)",
        },
        min_role="viewer",
    )


register_content_capabilities()
