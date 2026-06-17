import json
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.office import FileJsonPackage, FileJsonPatch
from app.core.exceptions import NotFound
from .json_version_service import JsonVersionService
from .patch_applicators import apply_text_patch, apply_excel_patch, apply_docx_patch, apply_pptx_patch, extract_excel_ref

logger = logging.getLogger(__name__)


class JsonPatchService:

    def __init__(self):
        self.version_svc = JsonVersionService()

    async def list_patches(self, db: AsyncSession, package_id: int) -> list[FileJsonPatch]:
        result = await db.execute(
            select(FileJsonPatch)
            .where(FileJsonPatch.package_id == package_id)
            .order_by(FileJsonPatch.created_at.desc())
        )
        return list(result.scalars().all())

    def validate_patch(self, patch: dict) -> dict:
        required = ["operation_type", "json_path", "after_content", "risk_level", "reason"]
        for field in required:
            if field not in patch or not str(patch.get(field, "")).strip():
                raise ValueError(f"缺少必填字段: {field}")
        if patch["risk_level"] not in ("low", "medium", "high"):
            raise ValueError("风险等级无效，仅支持 low/medium/high")
        return patch

    def preview_patch(self, patch: dict) -> dict:
        patch = self.validate_patch(patch)
        json_path = patch.get("json_path", "")
        if json_path.startswith("@excel:"):
            sheet, cell = extract_excel_ref(json_path)
            return {"preview_passed": True, "risk_level": patch["risk_level"], "sheet": sheet, "cell": cell}
        if json_path.startswith("$.content"):
            return {"preview_passed": True, "risk_level": patch["risk_level"]}
        return {"preview_passed": True, "risk_level": patch["risk_level"]}

    async def apply_patch(self, db: AsyncSession, patch: dict, package_id: int, user_id: int) -> dict:
        patch = self.validate_patch(patch)
        if patch["risk_level"] == "high":
            raise ValueError("风险等级过高，需要人工确认，本版暂不支持自动应用")

        pkg = await db.get(FileJsonPackage, package_id)
        if not pkg:
            raise NotFound("包不存在")
        current = await self.version_svc.get_current_version(db, package_id)
        if not current:
            raise NotFound("当前版本不存在")

        src_id = patch.get("source_version_id")
        if src_id and int(src_id) != (pkg.current_version_id or 0):
            raise ValueError("版本已过时，请刷新后重试")

        json_data = json.loads(current.json_content) if current.json_content else {}

        if patch["operation_type"] == "modify_cell":
            json_data = apply_excel_patch(json_data, patch)
        elif patch["json_path"].startswith("$.content"):
            pkg_type = (json_data.get("manifest") or {}).get("file_type", "")
            if pkg_type == "pptx":
                json_data = apply_pptx_patch(json_data, patch)
            else:
                json_data = apply_docx_patch(json_data, patch)
        else:
            json_data = apply_text_patch(json_data, patch)

        new_json = json.dumps(json_data, ensure_ascii=False, indent=2)
        new_version_id = await self.version_svc.create_version(
            db, package_id, new_json, patch.get("before_summary", ""), user_id,
        )

        patch_record = FileJsonPatch(
            package_id=package_id,
            source_version_id=pkg.current_version_id or current.id,
            target_version_id=new_version_id,
            operation_type=patch["operation_type"],
            json_path=patch["json_path"],
            before_summary=patch.get("before_summary", ""),
            after_content=patch["after_content"],
            risk_level=patch["risk_level"],
            reason=patch.get("reason", ""),
            patch_status="applied",
            creator_id=user_id,
        )
        db.add(patch_record)
        pkg.current_version_id = new_version_id

        new_version = await self.version_svc.get_version(db, new_version_id)
        await db.commit()

        return {
            "new_version_id": new_version_id,
            "new_version_number": new_version.version_number,
            "message": "补丁应用成功",
        }
