"""Content Pipeline service — orchestrates parse → package → resource extraction.

Triggered by:
- file.uploaded event (auto pipeline)
- content:pipeline capability (manual/retry)
- content:get_package lazy build (on-demand)
"""
import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.database import AsyncSessionLocal
from app.models.content import ContentPackage
from app.services.content.package_service import ContentPackageService
from app.services.content.resource_service import ResourceService
from app.services.file_reader import resolve_caller_user_id
from app.services.file_service import check_file_access

logger = logging.getLogger("v2.content").getChild("pipeline")

SUPPORTED_EXTENSIONS = {
    "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
    "csv", "tsv", "txt", "md", "markdown",
    "json", "yaml", "yml",
    "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg",
    "eml", "msg",
}


class ContentPipelineService:

    def __init__(self):
        self.package_svc = ContentPackageService()
        self.resource_svc = ResourceService()

    async def run_pipeline(
        self, file_id: int, caller: str,
    ) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            caller_user_id = resolve_caller_user_id(caller)
            file_record = await check_file_access(db, file_id, caller_user_id)

            ext = (file_record.extension or "").lower()
            if ext not in SUPPORTED_EXTENSIONS:
                return {
                    "skipped": True,
                    "reason": f"Unsupported format: {ext}",
                }

            # Get or create package
            pkg_info = await self.package_svc.get_or_create(
                db, file_id, file_record.owner_id, caller,
            )

            if pkg_info["status"] in ("parsed", "ready", "degraded"):
                # 源文件是否变过：比对真源字节 SHA-256（取代旧的 SHA256(md5)/MD5(md5) 假 hash，
                # 那对永不相等导致每次都重解析）。优先读上传写好的 FileRevision.sha256。
                from app.services.content.source_revision import resolve_source_sha256
                current_sha256 = await resolve_source_sha256(db, file_record)
                if pkg_info.get("source_hash") and pkg_info["source_hash"] == current_sha256:
                    return {
                        "package_id": pkg_info["id"],
                        "status": "already_parsed",
                    }

            # Run the actual pipeline
            result = await self.package_svc.run_pipeline(
                db, pkg_info["id"], caller,
            )

            # Extract resources from parse result
            await self._extract_resources(db, pkg_info["id"], caller)

            return {
                "package_id": result["id"],
                "status": result["status"],
            }

    async def run_pipeline_for_package(
        self, db: AsyncSession, package_id: int, caller: str,
    ) -> dict[str, Any]:
        pkg = await db.get(ContentPackage, package_id)
        if not pkg or pkg.deleted:
            raise NotFound(f"ContentPackage {package_id} not found")

        result = await self.package_svc.run_pipeline(db, package_id, caller)
        await self._extract_resources(db, package_id, caller)
        return result

    async def _extract_resources(
        self, db: AsyncSession, package_id: int, caller: str,
    ):
        pkg = await db.get(ContentPackage, package_id)
        if not pkg:
            return
        version = await self.package_svc._get_current_version(db, package_id)
        if not version or not version.content_json:
            return

        try:
            content_ir = json.loads(version.content_json)
        except (json.JSONDecodeError, TypeError):
            return

        blocks = content_ir.get("blocks", [])
        for block in self._iter_blocks(blocks):
            res_id = block.get("resource_ref")
            if res_id and isinstance(res_id, int):
                try:
                    await self.resource_svc.add_ref(
                        db, package_id, int(res_id),
                        block_id=block.get("id"),
                        version_id=version.id,
                    )
                except Exception as e:
                    logger.warning("Failed to add resource ref for resource_id=%s: %s", res_id, e)

    async def handle_file_uploaded(
        self, payload: dict, caller: str, caller_role: str,
    ) -> dict:
        file_id = payload.get("file_id")
        if not file_id:
            return {"error": "file_id required"}

        try:
            result = await self.run_pipeline(file_id, caller)
            logger.info("Content pipeline auto-triggered for file_id=%d: %s", file_id, result.get("status"))
            return result
        except Exception as e:
            logger.error("Content pipeline failed for file_id=%d: %s", file_id, e)
            return {"file_id": file_id, "error": str(e), "status": "failed"}

    def _iter_blocks(self, blocks: list[dict]):
        for b in blocks:
            yield b
            if b.get("children"):
                yield from self._iter_blocks(b["children"])
