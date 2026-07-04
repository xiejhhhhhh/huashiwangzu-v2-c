"""ContentPackage source-file lifecycle tests."""

import json
import uuid

import app.main  # noqa: F401 - registers content event handlers/capabilities
import pytest
from app.database import AsyncSessionLocal
from app.models.content import ContentPackage, ContentPackageVersion
from app.models.file import File
from app.services.content.package_lifecycle_service import (
    handle_file_deleted,
    handle_file_permanently_deleted,
    handle_file_restored,
)
from app.services.content.package_service import ContentPackageService
from sqlalchemy import delete


async def _cleanup(file_id: int | None, package_id: int | None) -> None:
    async with AsyncSessionLocal() as db:
        if package_id:
            await db.execute(delete(ContentPackageVersion).where(ContentPackageVersion.package_id == package_id))
            await db.execute(delete(ContentPackage).where(ContentPackage.id == package_id))
        if file_id:
            await db.execute(delete(File).where(File.id == file_id))
        await db.commit()


@pytest.mark.asyncio
async def test_content_package_archives_and_restores_with_source_file_lifecycle() -> None:
    owner_id = 4
    file_id = None
    package_id = None
    async with AsyncSessionLocal() as db:
        file = File(
            name=f"lifecycle-source-{uuid.uuid4().hex}",
            extension="txt",
            size=0,
            owner_id=owner_id,
            storage_path="lifecycle-source.txt",
            mime_type="text/plain",
            deleted=False,
        )
        db.add(file)
        await db.flush()
        package = ContentPackage(
            owner_id=owner_id,
            source_file_id=file.id,
            package_type="text",
            origin_type="generated",
            source_extension="txt",
            status="parsed",
            manifest_json=json.dumps({"title": "Lifecycle"}, ensure_ascii=False),
        )
        db.add(package)
        await db.flush()
        file_id = file.id
        package_id = package.id
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            deleted_result = await handle_file_deleted(db, file_id)
            package = await db.get(ContentPackage, package_id)
            assert deleted_result["matched_packages"] == 1
            assert package is not None
            assert package.deleted is False
            assert package.status == "archived"
            assert package.parse_error == "source_file_deleted"
            payload = ContentPackageService()._package_to_dict(package)
            assert payload["source_lifecycle_state"] == "source_recycled"
            assert payload["archived_by_lifecycle"] is True

        async with AsyncSessionLocal() as db:
            restored_result = await handle_file_restored(db, file_id)
            package = await db.get(ContentPackage, package_id)
            assert restored_result["changed_packages"] == 1
            assert package is not None
            assert package.status == "parsed"
            assert package.parse_error is None
            payload = ContentPackageService()._package_to_dict(package)
            assert payload["source_lifecycle_state"] == "source_available"
            assert payload["archived_by_lifecycle"] is False
    finally:
        await _cleanup(file_id, package_id)


@pytest.mark.asyncio
async def test_content_package_permanent_delete_event_is_idempotent_archive() -> None:
    owner_id = 4
    file_id = None
    package_id = None
    async with AsyncSessionLocal() as db:
        file = File(
            name=f"permanent-source-{uuid.uuid4().hex}",
            extension="txt",
            size=0,
            owner_id=owner_id,
            storage_path="permanent-source.txt",
            mime_type="text/plain",
            deleted=True,
        )
        db.add(file)
        await db.flush()
        package = ContentPackage(
            owner_id=owner_id,
            source_file_id=file.id,
            package_type="text",
            origin_type="generated",
            source_extension="txt",
            status="parsed",
        )
        db.add(package)
        await db.flush()
        file_id = file.id
        package_id = package.id
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            first = await handle_file_permanently_deleted(db, file_id)
            second = await handle_file_permanently_deleted(db, file_id)
            package = await db.get(ContentPackage, package_id)
            assert first["matched_packages"] == 1
            assert second["matched_packages"] == 1
            assert second["changed_packages"] == 0
            assert package is not None
            assert package.deleted is False
            assert package.status == "archived"
            assert package.parse_error == "source_file_permanently_deleted"
            payload = ContentPackageService()._package_to_dict(package)
            assert payload["source_lifecycle_state"] == "source_permanently_deleted"
            assert payload["source_available"] is False
    finally:
        await _cleanup(file_id, package_id)
