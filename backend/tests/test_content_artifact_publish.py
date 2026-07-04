"""ContentPackage publish artifact/file contract tests."""
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.artifact import Artifact, ArtifactOperation, ArtifactVersion
from app.models.content import ContentPackage, ContentPackageVersion, ResourceRef
from app.models.file import File
from app.routers.content import _cap_publish, publish_package
from app.schemas.content_package import PublishRequest
from app.services.content.export_service import ContentExportService
from app.services.content.ir_writer import write_ir
from sqlalchemy import delete, func, select


def _valid_document_ir(title: str = "Publish Artifact Test") -> dict:
    return {
        "schema_version": "1.0",
        "content_type": "document",
        "title": title,
        "blocks": [
            {"type": "heading", "text": title, "level": 1},
            {"type": "paragraph", "text": "Body text"},
        ],
    }


async def _delete_content_packages(db, package_ids: list[int]) -> None:
    if not package_ids:
        return
    await db.execute(delete(ResourceRef).where(ResourceRef.package_id.in_(package_ids)))
    await db.execute(delete(ContentPackageVersion).where(ContentPackageVersion.package_id.in_(package_ids)))
    await db.execute(delete(ContentPackage).where(ContentPackage.id.in_(package_ids)))
    await db.commit()


async def _delete_files(db, file_ids: list[int]) -> None:
    if not file_ids:
        return
    await db.execute(delete(File).where(File.id.in_(file_ids)))
    await db.commit()


async def _delete_artifacts(db, artifact_ids: list[int]) -> None:
    if not artifact_ids:
        return
    await db.execute(delete(ArtifactOperation).where(ArtifactOperation.artifact_id.in_(artifact_ids)))
    await db.execute(delete(ArtifactVersion).where(ArtifactVersion.artifact_id.in_(artifact_ids)))
    await db.execute(delete(Artifact).where(Artifact.id.in_(artifact_ids)))
    await db.commit()


async def _file_storage_paths(db, file_ids: list[int]) -> list[Path]:
    upload_root = Path(get_settings().UPLOAD_DIR).resolve()
    paths: list[Path] = []
    for file_id in file_ids:
        file_rec = await db.get(File, file_id)
        if file_rec and file_rec.storage_path:
            paths.append(upload_root / file_rec.storage_path)
    return paths


async def _write_text_package(db, owner_id: int, title: str) -> int:
    result = await write_ir(
        db,
        _valid_document_ir(title),
        owner_id=owner_id,
        caller=f"user:{owner_id}",
    )
    package = await db.get(ContentPackage, result["package_id"])
    assert package is not None
    package.source_extension = "txt"
    await db.commit()
    return int(result["package_id"])


def _compiled_temp_file(content: bytes) -> Path:
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt")
    os.close(tmp_fd)
    path = Path(tmp_path)
    path.write_bytes(content)
    return path


def _unique_bytes(label: str) -> bytes:
    return f"{label}-{uuid.uuid4().hex}".encode("utf-8")


@pytest.mark.asyncio
async def test_content_publish_non_owner_does_not_create_artifact_or_file():
    owner_id = 4
    other_user_id = 5
    package_id: int | None = None

    async with AsyncSessionLocal() as db:
        package_id = await _write_text_package(
            db,
            owner_id,
            f"Publish Permission {uuid.uuid4().hex}",
        )
        before_files = await db.scalar(select(func.count()).select_from(File))
        before_artifacts = await db.scalar(select(func.count()).select_from(Artifact))

    try:
        envelope = await _cap_publish({"package_id": package_id}, f"user:{other_user_id}")

        assert envelope["success"] is False
        assert "permission" in envelope["error"].lower()

        async with AsyncSessionLocal() as db:
            after_files = await db.scalar(select(func.count()).select_from(File))
            after_artifacts = await db.scalar(select(func.count()).select_from(Artifact))

        assert after_files == before_files
        assert after_artifacts == before_artifacts
    finally:
        async with AsyncSessionLocal() as db:
            if package_id is not None:
                await _delete_content_packages(db, [package_id])


@pytest.mark.asyncio
async def test_publish_without_target_returns_artifact_file_contract():
    owner_id = 4
    package_id: int | None = None
    artifact_ids: list[int] = []
    file_ids: list[int] = []
    storage_paths: list[Path] = []
    content = _unique_bytes("published-file-content")
    compiled_path = _compiled_temp_file(content)

    async with AsyncSessionLocal() as db:
        try:
            package_id = await _write_text_package(db, owner_id, f"Publish New {uuid.uuid4().hex}")
            before_files = await db.scalar(select(func.count()).select_from(File))

            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file",
                return_value=(compiled_path, f"published-{uuid.uuid4().hex}.txt"),
            ):
                published = await ContentExportService().publish(
                    db,
                    package_id,
                    owner_id=owner_id,
                )

            file_ids.append(published["file_id"])
            artifact_ids.append(published["artifact_id"])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            after_files = await db.scalar(select(func.count()).select_from(File))

            artifact = await db.get(Artifact, published["artifact_id"])
            published_file = await db.get(File, published["file_id"])
            assert artifact is not None
            versions = (
                await db.execute(select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact.id))
            ).scalars().all()
            operations = (
                await db.execute(select(ArtifactOperation).where(ArtifactOperation.artifact_id == artifact.id))
            ).scalars().all()
            package = await db.get(ContentPackage, package_id)
            assert package is not None
            manifest = json.loads(package.manifest_json or "{}")

            assert after_files == (before_files or 0) + 1
            assert published["package_id"] == package_id
            assert published["artifact_id"] == published["artifact"]["id"]
            assert published["artifact"]["artifact_id"] == published["artifact_id"]
            assert published["artifact"]["package_id"] == package_id
            assert published["artifact"]["origin_module"] == "content"
            assert published["artifact"]["source_file_id"] is None
            assert published["file_id"] == artifact.file_id
            assert published["download_url"] == f"/api/files/download/{published['file_id']}"
            assert published["open_url"] == f"/api/files/preview/{published['file_id']}"
            assert published["desktop_visible"] is True
            assert published["artifact"]["download_url"] == published["download_url"]
            assert published["artifact"]["open_url"] == published["open_url"]
            assert published["artifact"]["desktop_visible"] is True
            assert published["published_version_id"] == artifact.current_version_id
            assert published["source_file_id"] is None
            assert published["origin_module"] == "content"
            assert published["status"] == "published"
            assert published["publish_status"] == "published_artifact/file"
            assert published_file is not None
            assert published_file.owner_id == owner_id
            assert published_file.deleted is False
            assert published_file.folder_id is None
            assert published_file.extension == "txt"
            assert artifact.storage_mode == "file"
            assert artifact.source_module == "content"
            assert artifact.source_object_type == "content_package"
            assert artifact.source_object_id == package_id
            assert len(versions) == 1
            assert versions[0].id == artifact.current_version_id
            assert versions[0].file_id == published["file_id"]
            assert [op.operation_type for op in operations] == ["create"]
            assert manifest["publish"]["artifact_id"] == artifact.id
            assert manifest["publish"]["file_id"] == published["file_id"]
            assert manifest["publish"]["published_version_id"] == artifact.current_version_id
            assert manifest["publish"]["download_url"] == published["download_url"]
            assert manifest["publish"]["open_url"] == published["open_url"]
            assert manifest["publish"]["desktop_visible"] is True
        finally:
            await _delete_artifacts(db, artifact_ids)
            if package_id is not None:
                await _delete_content_packages(db, [package_id])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            await _delete_files(db, file_ids)
            for path in set(storage_paths):
                path.unlink(missing_ok=True)
            compiled_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_publish_write_ir_package_without_source_file_creates_artifact_file():
    owner_id = 4
    package_id: int | None = None
    artifact_ids: list[int] = []
    file_ids: list[int] = []
    storage_paths: list[Path] = []
    content = _unique_bytes("generated-package-publish")
    compiled_path = _compiled_temp_file(content)

    async with AsyncSessionLocal() as db:
        try:
            package_id = await _write_text_package(
                db,
                owner_id,
                f"Generated Publish {uuid.uuid4().hex}",
            )
            package = await db.get(ContentPackage, package_id)
            assert package is not None
            package.source_extension = ""
            await db.commit()

            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file",
                return_value=(compiled_path, f"generated-{uuid.uuid4().hex}.txt"),
            ) as compile_mock:
                published = await ContentExportService().publish(
                    db,
                    package_id,
                    owner_id=owner_id,
                )

            file_ids.append(published["file_id"])
            artifact_ids.append(published["artifact_id"])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            artifact = await db.get(Artifact, published["artifact_id"])
            package_response = await ContentExportService().package_svc.get_package(
                db,
                package_id=package_id,
                owner_id=owner_id,
            )

            compile_mock.assert_called_once()
            assert published["status"] == "published"
            assert published["format"] == "txt"
            assert published["publish_status"] == "published_artifact/file"
            assert published["download_url"] == f"/api/files/download/{published['file_id']}"
            assert published["open_url"] == f"/api/files/preview/{published['file_id']}"
            assert published["desktop_visible"] is True
            assert artifact is not None
            assert artifact.file_id == published["file_id"]
            assert package_response["published_artifact_id"] == published["artifact_id"]
            assert package_response["published_file_id"] == published["file_id"]
            assert package_response["download_url"] == published["download_url"]
            assert package_response["open_url"] == published["open_url"]
            assert package_response["desktop_visible"] is True
            assert storage_paths[-1].read_bytes() == content
        finally:
            await _delete_artifacts(db, artifact_ids)
            if package_id is not None:
                await _delete_content_packages(db, [package_id])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            await _delete_files(db, file_ids)
            for path in set(storage_paths):
                path.unlink(missing_ok=True)
            compiled_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_content_publish_capability_returns_artifact_file_envelope():
    owner_id = 4
    package_id: int | None = None
    artifact_ids: list[int] = []
    file_ids: list[int] = []
    storage_paths: list[Path] = []
    content = _unique_bytes("capability-publish")
    compiled_path = _compiled_temp_file(content)

    async with AsyncSessionLocal() as db:
        package_id = await _write_text_package(
            db,
            owner_id,
            f"Capability Publish {uuid.uuid4().hex}",
        )

    try:
        with mock.patch(
            "app.services.content.export_service.ContentExportService._compile_to_file",
            return_value=(compiled_path, f"capability-{uuid.uuid4().hex}.txt"),
        ):
            envelope = await _cap_publish({"package_id": package_id}, f"user:{owner_id}")

        assert envelope["success"] is True
        published = envelope["data"]
        file_ids.append(published["file_id"])
        artifact_ids.append(published["artifact_id"])

        assert published["package_id"] == package_id
        assert published["artifact_id"] == published["artifact"]["id"]
        assert published["artifact"]["artifact_id"] == published["artifact_id"]
        assert published["artifact"]["package_id"] == package_id
        assert published["artifact"]["origin_module"] == "content"
        assert published["file_id"] == published["artifact"]["file_id"]
        assert published["download_url"] == f"/api/files/download/{published['file_id']}"
        assert published["open_url"] == f"/api/files/preview/{published['file_id']}"
        assert published["published_version_id"] == published["artifact"]["current_version_id"]
        assert published["status"] == "published"
        assert published["publish_status"] == "published_artifact/file"
        assert published["desktop_visible"] is True

        async with AsyncSessionLocal() as db:
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            assert storage_paths[-1].read_bytes() == content
    finally:
        async with AsyncSessionLocal() as db:
            await _delete_artifacts(db, artifact_ids)
            if package_id is not None:
                await _delete_content_packages(db, [package_id])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            await _delete_files(db, file_ids)
        for path in set(storage_paths):
            path.unlink(missing_ok=True)
        compiled_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_rest_publish_handler_returns_artifact_file_response():
    owner_id = 4
    package_id: int | None = None
    artifact_ids: list[int] = []
    file_ids: list[int] = []
    storage_paths: list[Path] = []
    content = _unique_bytes("rest-publish")
    compiled_path = _compiled_temp_file(content)

    async with AsyncSessionLocal() as db:
        try:
            package_id = await _write_text_package(
                db,
                owner_id,
                f"Rest Publish {uuid.uuid4().hex}",
            )

            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file",
                return_value=(compiled_path, f"rest-{uuid.uuid4().hex}.txt"),
            ):
                response = await publish_package(
                    package_id,
                    PublishRequest(),
                    db,
                    SimpleNamespace(id=owner_id),
                )

            assert response.success is True
            published = response.data
            assert published is not None
            file_ids.append(published["file_id"])
            artifact_ids.append(published["artifact_id"])
            storage_paths.extend(await _file_storage_paths(db, file_ids))

            assert published["package_id"] == package_id
            assert published["artifact_id"] == published["artifact"]["id"]
            assert published["artifact"]["package_id"] == package_id
            assert published["artifact"]["origin_module"] == "content"
            assert published["file_id"] == published["artifact"]["file_id"]
            assert published["download_url"] == f"/api/files/download/{published['file_id']}"
            assert published["open_url"] == f"/api/files/preview/{published['file_id']}"
            assert published["published_version_id"] == published["artifact"]["current_version_id"]
            assert published["status"] == "published"
            assert published["publish_status"] == "published_artifact/file"
            assert published["desktop_visible"] is True
            assert storage_paths[-1].read_bytes() == content
        finally:
            await _delete_artifacts(db, artifact_ids)
            if package_id is not None:
                await _delete_content_packages(db, [package_id])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            await _delete_files(db, file_ids)
            for path in set(storage_paths):
                path.unlink(missing_ok=True)
            compiled_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_publish_to_target_records_artifact_versions_and_operation():
    owner_id = 4
    package_id: int | None = None
    target_file_id: int | None = None
    artifact_ids: list[int] = []
    file_ids: list[int] = []
    storage_paths: list[Path] = []
    content = _unique_bytes("published-target-content")
    compiled_path = _compiled_temp_file(content)

    async with AsyncSessionLocal() as db:
        try:
            target = File(
                name=f"content-publish-target-{uuid.uuid4().hex}",
                extension="txt",
                size=3,
                owner_id=owner_id,
                storage_path=f"test/missing-{uuid.uuid4().hex}.txt",
                mime_type="text/plain",
                md5_hash=hashlib.md5(b"old").hexdigest(),
                deleted=False,
            )
            db.add(target)
            await db.commit()
            await db.refresh(target)
            target_file_id = target.id
            file_ids.append(target_file_id)
            package_id = await _write_text_package(db, owner_id, "Publish Target")
            before_files = await db.scalar(select(func.count()).select_from(File))

            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file",
                return_value=(compiled_path, "compiled.txt"),
            ):
                published = await ContentExportService().publish(
                    db,
                    package_id,
                    target_file_id=target_file_id,
                    owner_id=owner_id,
                )

            artifact_ids.append(published["artifact_id"])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            after_files = await db.scalar(select(func.count()).select_from(File))
            refreshed_file = await db.get(File, target_file_id)
            artifact = await db.get(Artifact, published["artifact_id"])
            assert artifact is not None
            versions = (
                await db.execute(
                    select(ArtifactVersion)
                    .where(ArtifactVersion.artifact_id == artifact.id)
                    .order_by(ArtifactVersion.version_no)
                )
            ).scalars().all()
            operations = (
                await db.execute(
                    select(ArtifactOperation)
                    .where(ArtifactOperation.artifact_id == artifact.id)
                    .order_by(ArtifactOperation.id)
                )
            ).scalars().all()

            assert after_files == before_files
            assert refreshed_file is not None
            assert refreshed_file.size == len(content)
            assert refreshed_file.md5_hash == hashlib.md5(content).hexdigest()
            assert published["status"] == "replaced"
            assert published["file_id"] == target_file_id
            assert published["target_file_id"] == target_file_id
            assert published["download_url"] == f"/api/files/download/{target_file_id}"
            assert published["open_url"] == f"/api/files/preview/{target_file_id}"
            assert published["desktop_visible"] is True
            assert published["artifact_id"] == artifact.id
            assert published["published_version_id"] == artifact.current_version_id
            assert artifact.file_id == target_file_id
            assert artifact.source_module == "content"
            assert artifact.source_object_type == "content_package"
            assert artifact.source_object_id == package_id
            assert len(versions) == 2
            assert versions[-1].id == artifact.current_version_id
            assert versions[-1].file_id == target_file_id
            assert versions[-1].size == len(content)
            assert versions[-1].binary_hash == hashlib.sha256(content).hexdigest()
            assert [op.operation_type for op in operations] == ["create", "publish_replace"]
            assert storage_paths[-1].read_bytes() == content
        finally:
            await _delete_artifacts(db, artifact_ids)
            if package_id is not None:
                await _delete_content_packages(db, [package_id])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            await _delete_files(db, file_ids)
            for path in set(storage_paths):
                path.unlink(missing_ok=True)
            compiled_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_publish_to_same_target_reuses_artifact_and_appends_versions():
    owner_id = 4
    package_id: int | None = None
    target_file_id: int | None = None
    artifact_ids: list[int] = []
    file_ids: list[int] = []
    storage_paths: list[Path] = []
    first_content = _unique_bytes("first-target-publish")
    second_content = _unique_bytes("second-target-publish")
    first_path = _compiled_temp_file(first_content)
    second_path = _compiled_temp_file(second_content)

    async with AsyncSessionLocal() as db:
        try:
            target = File(
                name=f"content-publish-reuse-{uuid.uuid4().hex}",
                extension="txt",
                size=3,
                owner_id=owner_id,
                storage_path=f"test/missing-{uuid.uuid4().hex}.txt",
                mime_type="text/plain",
                md5_hash=hashlib.md5(b"old").hexdigest(),
                deleted=False,
            )
            db.add(target)
            await db.commit()
            await db.refresh(target)
            target_file_id = target.id
            file_ids.append(target_file_id)
            package_id = await _write_text_package(db, owner_id, "Publish Target Reuse")
            before_files = await db.scalar(select(func.count()).select_from(File))

            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file",
                return_value=(first_path, "first.txt"),
            ):
                first = await ContentExportService().publish(
                    db,
                    package_id,
                    target_file_id=target_file_id,
                    owner_id=owner_id,
                )
            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file",
                return_value=(second_path, "second.txt"),
            ):
                second = await ContentExportService().publish(
                    db,
                    package_id,
                    target_file_id=target_file_id,
                    owner_id=owner_id,
                )

            artifact_ids.append(first["artifact_id"])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            after_files = await db.scalar(select(func.count()).select_from(File))
            refreshed_file = await db.get(File, target_file_id)
            versions = (
                await db.execute(
                    select(ArtifactVersion)
                    .where(ArtifactVersion.artifact_id == first["artifact_id"])
                    .order_by(ArtifactVersion.version_no)
                )
            ).scalars().all()
            artifacts = (
                await db.execute(
                    select(Artifact).where(
                        Artifact.owner_id == owner_id,
                        Artifact.source_module == "content",
                        Artifact.source_object_type == "content_package",
                        Artifact.source_object_id == package_id,
                    )
                )
            ).scalars().all()

            assert after_files == before_files
            assert first["artifact_id"] == second["artifact_id"]
            assert first["file_id"] == second["file_id"] == target_file_id
            assert second["published_version_id"] != first["published_version_id"]
            assert len(artifacts) == 1
            assert len(versions) == 4
            assert versions[-1].id == second["published_version_id"]
            assert refreshed_file is not None
            assert refreshed_file.md5_hash == hashlib.md5(second_content).hexdigest()
            assert storage_paths[-1].read_bytes() == second_content
        finally:
            await _delete_artifacts(db, artifact_ids)
            if package_id is not None:
                await _delete_content_packages(db, [package_id])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            await _delete_files(db, file_ids)
            for path in set(storage_paths):
                path.unlink(missing_ok=True)
            first_path.unlink(missing_ok=True)
            second_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_package_response_publish_status_state_machine():
    owner_id = 4
    package_id: int | None = None
    artifact_ids: list[int] = []
    file_ids: list[int] = []
    storage_paths: list[Path] = []
    content = _unique_bytes("state-machine-publish")
    compiled_path = _compiled_temp_file(content)

    async with AsyncSessionLocal() as db:
        try:
            package = ContentPackage(
                owner_id=owner_id,
                source_file_id=None,
                package_type="text",
                origin_type="generated",
                source_extension="txt",
                package_version="1.0",
                status="pending",
            )
            db.add(package)
            await db.commit()
            await db.refresh(package)
            package_id = package.id

            draft = await ContentExportService().package_svc.get_package(
                db,
                package_id=package_id,
                owner_id=owner_id,
            )
            assert draft["publish_status"] == "draft_package"

            version = ContentPackageVersion(
                package_id=package_id,
                version_no=1,
                content_json=json.dumps({
                    "manifest": {"title": "State Machine Publish"},
                    "blocks": [{"id": "p1", "type": "paragraph", "text": "state"}],
                }),
                operation_type="write_ir",
                created_by=owner_id,
            )
            db.add(version)
            await db.flush()
            package.current_version_id = version.id
            package.status = "parsed"
            await db.commit()

            preview = await ContentExportService().package_svc.get_package(
                db,
                package_id=package_id,
                owner_id=owner_id,
            )
            assert preview["publish_status"] == "compiled_preview"

            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file",
                return_value=(compiled_path, f"state-machine-{uuid.uuid4().hex}.txt"),
            ):
                published = await ContentExportService().publish(
                    db,
                    package_id,
                    owner_id=owner_id,
                )

            artifact_ids.append(published["artifact_id"])
            file_ids.append(published["file_id"])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            package_response = await ContentExportService().package_svc.get_package(
                db,
                package_id=package_id,
                owner_id=owner_id,
            )

            assert package_response["publish_status"] == "published_artifact/file"
            assert package_response["published_artifact_id"] == published["artifact_id"]
            assert package_response["published_file_id"] == published["file_id"]
            assert package_response["published_version_id"] == published["published_version_id"]
            assert package_response["download_url"] == published["download_url"]
            assert package_response["open_url"] == published["open_url"]
            assert package_response["desktop_visible"] is True
        finally:
            await _delete_artifacts(db, artifact_ids)
            if package_id is not None:
                await _delete_content_packages(db, [package_id])
            storage_paths.extend(await _file_storage_paths(db, file_ids))
            await _delete_files(db, file_ids)
            for path in set(storage_paths):
                path.unlink(missing_ok=True)
            compiled_path.unlink(missing_ok=True)
