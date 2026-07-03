"""Content Export service — recompile Content Package → physical file.

Content Package is the canonical source; export adapters call format modules
to produce physical Office/image/text files.
"""
import logging
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import NotFound, ValidationError
from app.services.content.package_service import ContentPackageService
from app.services.file_service import check_file_access, get_file_record
from app.services.file_upload_service import upload_file_from_path

logger = logging.getLogger("v2.content").getChild("export")

EXPORT_ADAPTER_MAP: dict[str, str] = {
    "docx": "docx",
    "xlsx": "xlsx",
    "pptx": "pptx",
    "pdf": "pdf",
    "txt": "txt",
    "md": "txt",
    "csv": "csv",
    "html": "html",
}


class ContentExportService:

    def __init__(self):
        self.package_svc = ContentPackageService()

    async def export(
        self, db: AsyncSession, package_id: int,
        target_format: str | None = None,
        owner_id: int | None = None,
        conflict_policy: str = "auto_rename",
    ) -> dict[str, Any]:
        pkg_info = await self.package_svc.get_package(
            db, package_id=package_id, owner_id=owner_id,
        )

        fmt = (target_format or pkg_info["source_extension"]).lower().strip(".")

        if fmt not in EXPORT_ADAPTER_MAP:
            if fmt in {"doc", "ppt", "xls"}:
                fmt = fmt + "x"
            if fmt not in EXPORT_ADAPTER_MAP:
                return await self._fallback_copy(db, pkg_info, owner_id)

        full = await self.package_svc.get_full_package(
            db, package_id, owner_id=owner_id,
        )
        content = full.get("content", {})

        file_path, filename = await self._compile_to_file(
            db, pkg_info, fmt, content, owner_id,
        )

        try:
            result = await upload_file_from_path(
                db, file_path, filename, pkg_info["owner_id"],
                md5_hex=None,
            )
        except Exception as e:
            if "already exists" in str(e) and conflict_policy == "auto_rename":
                import time

                name_part, ext_part = filename.rsplit(".", 1)
                last_error = e
                for attempt in range(10):
                    renamed = f"{name_part}_{time.time_ns()}_{attempt}.{ext_part}"
                    try:
                        result = await upload_file_from_path(
                            db, file_path, renamed, pkg_info["owner_id"],
                            md5_hex=None,
                        )
                        filename = renamed
                        break
                    except Exception as retry_error:
                        if "already exists" not in str(retry_error):
                            raise
                        last_error = retry_error
                else:
                    raise last_error
            elif "already exists" in str(e) and conflict_policy == "overwrite":
                from sqlalchemy import select

                from app.models.file import File
                r = await db.execute(
                    select(File).where(
                        File.name == filename.rsplit(".", 1)[0],
                        File.extension == fmt,
                        File.owner_id == pkg_info["owner_id"],
                        File.deleted.is_(False),
                    )
                )
                existing = r.scalar_one_or_none()
                if existing:
                    from app.services.file_upload_service import replace_file_content
                    content_bytes = file_path.read_bytes()
                    await replace_file_content(db, existing.id, pkg_info["owner_id"], content_bytes)
                    result = {"id": existing.id}
                else:
                    result = await upload_file_from_path(
                        db, file_path, filename, pkg_info["owner_id"],
                        md5_hex=None,
                    )
            else:
                raise

        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass

        return {
            "file_id": result["id"],
            "file_name": filename,
            "package_id": package_id,
            "format": fmt,
        }

    async def publish(
        self, db: AsyncSession, package_id: int,
        target_file_id: int | None = None,
        owner_id: int | None = None,
        conflict_policy: str = "create_version",
    ) -> dict[str, Any]:
        export_result = await self.export(db, package_id, owner_id=owner_id)

        from app.services.artifact_service import create_artifact
        artifact = await create_artifact(
            db,
            owner_id=owner_id or 0,
            name=export_result["file_name"].rsplit(".", 1)[0],
            extension=export_result["file_name"].rsplit(".", 1)[-1] if "." in export_result["file_name"] else "",
            file_id=export_result["file_id"],
            source_module="content",
            source_object_type="content_package",
            source_object_id=package_id,
            conflict_policy=conflict_policy,
        )

        return {
            "artifact": artifact,
            "file_id": export_result["file_id"],
            "package_id": package_id,
        }

    async def _compile_to_file(
        self, db: AsyncSession,
        pkg_info: dict, fmt: str, content: dict,
        owner_id: int | None = None,
    ) -> tuple[Path, str]:
        settings = get_settings()
        tmp_dir = Path(settings.UPLOAD_DIR).resolve().parent / ".tmp_exports"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        base_name = pkg_info.get("manifest", {}).get("title", "export") or "export"
        filename = f"{base_name}.{fmt}"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{fmt}", dir=str(tmp_dir))
        tmp_file = Path(tmp_path)

        adapter_type = EXPORT_ADAPTER_MAP.get(fmt, "txt")

        if adapter_type in ("docx", "xlsx", "pptx", "pdf"):
            blocks = content.get("blocks", [])

            adapter_payload = {
                "filename": base_name,
            }

            if adapter_type == "docx":
                adapter_payload["content"] = self._blocks_to_docx_content(blocks)
            elif adapter_type == "xlsx":
                adapter_payload["sheets"] = self._blocks_to_sheets(blocks)
            elif adapter_type == "pptx":
                adapter_payload["slides"] = self._blocks_to_slides(blocks)
            elif adapter_type == "pdf":
                adapter_payload["content"] = self._blocks_to_docx_content(blocks)

            from app.services.content.adapter import call_export_adapter
            result = await call_export_adapter(
                db, adapter_type, adapter_payload, owner_id or 0,
            )

            if result.get("file_path"):
                return Path(result["file_path"]), filename

        # Text fallback
        text_content = self._blocks_to_text(content.get("blocks", []))
        tmp_file.write_text(text_content, encoding="utf-8")

        return tmp_file, filename

    def _blocks_to_text(self, blocks: list[dict]) -> str:
        parts = []
        for b in blocks:
            text = b.get("text", "")
            if text:
                parts.append(text)
            if b.get("children"):
                parts.append(self._blocks_to_text(b["children"]))
        return "\n\n".join(parts)

    def _blocks_to_docx_content(self, blocks: list[dict]) -> list[dict]:
        result = []
        for b in blocks:
            item = {
                "type": b.get("type", "paragraph"),
                "text": b.get("text", ""),
            }
            if "level" in b.get("data", {}):
                item["level"] = b["data"]["level"]
            result.append(item)
            if b.get("children"):
                result.extend(self._blocks_to_docx_content(b["children"]))
        return result

    def _blocks_to_sheets(self, blocks: list[dict]) -> list[dict]:
        sheets = []
        current_sheet = None
        for b in blocks:
            if b.get("type") == "sheet":
                if current_sheet:
                    sheets.append(current_sheet)
                current_sheet = {
                    "name": b.get("text", "Sheet1"),
                    "columns": [],
                    "rows": [],
                }
            elif b.get("type") == "cell" and current_sheet is not None:
                pass
            elif b.get("type") == "table":
                if current_sheet is None:
                    current_sheet = {"name": "Sheet1", "columns": [], "rows": []}
                rows_data = b.get("data", {}).get("rows", [])
                if rows_data and not current_sheet["columns"]:
                    current_sheet["columns"] = [{"name": str(i)} for i in range(len(rows_data[0]))]
                current_sheet["rows"].extend(rows_data)
        if current_sheet:
            sheets.append(current_sheet)
        return sheets

    def _blocks_to_slides(self, blocks: list[dict]) -> list[dict]:
        slides = []
        current_slide = None
        for b in blocks:
            if b.get("type") == "slide":
                if current_slide:
                    slides.append(current_slide)
                current_slide = {
                    "name": b.get("text", f"Slide {len(slides) + 1}"),
                    "elements": [],
                }
            elif b.get("type") in ("heading", "paragraph", "textbox", "image") and current_slide is not None:
                elem = {
                    "type": b.get("type", "textbox"),
                    "text": b.get("text", ""),
                }
                if b.get("resource_ref"):
                    elem["resource_ref"] = b["resource_ref"]
                if b.get("data", {}).get("level"):
                    elem["level"] = b["data"]["level"]
                current_slide["elements"].append(elem)
            elif b.get("type") in ("heading", "paragraph", "textbox", "image"):
                current_slide = {
                    "name": f"Slide {len(slides) + 1}",
                    "elements": [{
                        "type": b.get("type", "textbox"),
                        "text": b.get("text", ""),
                    }],
                }
        if current_slide:
            slides.append(current_slide)
        return slides

    async def _fallback_copy(
        self, db: AsyncSession, pkg_info: dict, owner_id: int | None = None,
    ) -> dict[str, Any]:
        file_id = pkg_info.get("source_file_id")
        if not file_id:
            raise ValidationError("No source file to copy")

        file_record = await get_file_record(db, file_id)
        if not file_record:
            raise NotFound(f"Source file {file_id} not found")
        await check_file_access(db, file_id, owner_id or pkg_info["owner_id"])

        from app.services.file_preview_service import _resolve_storage_path
        safe_path = _resolve_storage_path(file_record)
        if not safe_path:
            raise NotFound("Source file not found on disk")

        from app.services.file_upload_service import upload_file_from_path
        result = await upload_file_from_path(
            db, Path(safe_path),
            f"{file_record.name}.{file_record.extension}" if file_record.extension else file_record.name,
            pkg_info["owner_id"],
        )
        return {
            "file_id": result["id"],
            "file_name": f"{file_record.name}.{file_record.extension}",
            "package_id": pkg_info["id"],
            "format": file_record.extension or "",
        }
