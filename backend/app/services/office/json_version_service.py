import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.office import FileJsonVersion, FileJsonPackage
from app.core.exceptions import NotFound

logger = logging.getLogger(__name__)


class JsonVersionService:

    async def list_versions(self, db: AsyncSession, package_id: int) -> list[FileJsonVersion]:
        result = await db.execute(
            select(FileJsonVersion)
            .where(FileJsonVersion.package_id == package_id)
            .order_by(FileJsonVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def create_version(
        self, db: AsyncSession, package_id: int, json_content: str,
        summary: str | None, creator_id: int
    ) -> int:
        result = await db.execute(
            select(func.max(FileJsonVersion.version_number))
            .where(FileJsonVersion.package_id == package_id)
        )
        max_version = result.scalar() or 0
        version_number = max_version + 1

        version = FileJsonVersion(
            package_id=package_id,
            version_number=version_number,
            json_content=json_content,
            summary=summary,
            creator_id=creator_id,
        )
        db.add(version)
        await db.flush()
        return version.id

    async def get_version(self, db: AsyncSession, version_id: int) -> FileJsonVersion | None:
        return await db.get(FileJsonVersion, version_id)

    async def get_current_version(self, db: AsyncSession, package_id: int) -> FileJsonVersion | None:
        pkg = await db.get(FileJsonPackage, package_id)
        if not pkg or not pkg.current_version_id:
            return None
        return await self.get_version(db, pkg.current_version_id)

    async def rollback(
        self, db: AsyncSession, package_id: int, target_version_id: int, user_id: int
    ) -> dict:
        pkg = await db.get(FileJsonPackage, package_id)
        if not pkg:
            raise NotFound("包不存在")

        target = await self.get_version(db, target_version_id)
        if not target or target.package_id != package_id:
            raise NotFound("目标版本不存在")

        new_version_id = await self.create_version(
            db, package_id, target.json_content,
            f"回滚至版本 {target.version_number}", user_id,
        )
        pkg.current_version_id = new_version_id

        new_version = await self.get_version(db, new_version_id)
        await db.commit()

        return {
            "new_version_id": new_version_id,
            "new_version_number": new_version.version_number,
            "message": "回滚成功",
        }
