import json
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.office import FileJsonPackage
from app.models.file import File
from app.core.exceptions import NotFound
from .json_version_service import JsonVersionService

logger = logging.getLogger(__name__)


class JsonPackageService:

    def __init__(self):
        self.version_svc = JsonVersionService()

    async def get_status(self, db: AsyncSession, file_id: int) -> FileJsonPackage | None:
        result = await db.execute(
            select(FileJsonPackage).where(FileJsonPackage.file_id == file_id)
        )
        return result.scalar_one_or_none()

    async def create_package(self, db: AsyncSession, file_id: int, user_id: int) -> dict:
        file = await db.get(File, file_id)
        if not file or file.deleted:
            raise NotFound("文件不存在或已删除")

        fmt = file.extension.lower() if file.extension else ""
        supported = {"docx", "xlsx", "pptx", "txt", "csv"}
        if fmt not in supported:
            raise ValueError(f"不支持的格式: {fmt}")

        json_content = json.dumps({
            "manifest": {
                "file_type": fmt, "version": "1.0.0",
                "file_name": f"{file.name}.{file.extension}",
            },
            "content": {},
        }, ensure_ascii=False, indent=2)

        existing = await self.get_status(db, file_id)

        if existing:
            version_id = await self.version_svc.create_version(
                db, existing.id, json_content, file.name[:200], user_id,
            )
            existing.current_version_id = version_id
            existing.package_status = "可用"
            package_id = existing.id
        else:
            pkg = FileJsonPackage(
                file_id=file_id, format_type=fmt,
                package_status="可用", current_version_id=None,
                creator_id=user_id,
            )
            db.add(pkg)
            await db.flush()

            version_id = await self.version_svc.create_version(
                db, pkg.id, json_content, file.name[:200], user_id,
            )
            pkg.current_version_id = version_id
            package_id = pkg.id

        await db.commit()
        return {"package_id": package_id, "version_id": version_id, "package_status": "可用"}

    async def read_package(self, db: AsyncSession, package_id: int) -> dict | None:
        pkg = await db.get(FileJsonPackage, package_id)
        if not pkg:
            return None

        version = await self.version_svc.get_current_version(db, package_id)
        if not version:
            return None

        json_content = json.loads(version.json_content) if version.json_content else {}

        return {
            "package": {
                "id": pkg.id, "file_id": pkg.file_id,
                "format_type": pkg.format_type,
                "package_status": pkg.package_status,
                "summary": pkg.summary,
            },
            "version": {
                "id": version.id, "version_number": version.version_number,
                "summary": version.summary,
                "created_at": version.created_at.isoformat() if version.created_at else None,
            },
            "json_content": json_content,
        }
