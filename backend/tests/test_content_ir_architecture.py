"""Content IR architecture integration tests.

Covers validator, writer, compile, download, and Agent policy.
"""
import base64
import hashlib
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest import mock

import app.main  # noqa: F401 - import side effect registers module capabilities
import pytest

# Add repo root to allow importing modules
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from app.core.exceptions import ConflictError
from app.core.exceptions import ValidationError as AppValidationError
from app.services.content.ir_normalizer import normalize_parser_output
from app.services.content.ir_validator import validate_ir, validate_ir_sync
from app.services.content.ir_writer import write_ir

# ── Helpers ──────────────────────────────────────────────────────────


def _valid_document_ir(**overrides) -> dict:
    ir = {
        "schema_version": "1.0",
        "content_type": "document",
        "title": "Test Document",
        "blocks": [
            {"type": "heading", "text": "Title", "level": 1},
            {"type": "paragraph", "text": "Body text"},
            {"type": "table", "data": {"headers": ["A", "B"], "rows": [["1", "2"]]}},
        ],
    }
    ir.update(overrides)
    return ir


def _valid_spreadsheet_ir(**overrides) -> dict:
    ir = {
        "schema_version": "1.0",
        "content_type": "spreadsheet",
        "title": "Test Sheet",
        "blocks": [
            {
                "type": "sheet",
                "text": "Sheet1",
                "children": [
                    {
                        "type": "table",
                        "data": {
                            "start_cell": "A1",
                            "headers": ["日期", "产品"],
                            "rows": [["2026-07-01", "A"]],
                        },
                    }
                ],
            }
        ],
    }
    ir.update(overrides)
    return ir


def _valid_presentation_ir(**overrides) -> dict:
    ir = {
        "schema_version": "1.0",
        "content_type": "presentation",
        "title": "Test Deck",
        "blocks": [
            {
                "type": "slide",
                "children": [
                    {"type": "heading", "text": "Slide 1", "level": 1},
                    {"type": "paragraph", "text": "Content"},
                ],
            }
        ],
    }
    ir.update(overrides)
    return ir


async def _delete_content_packages(db, package_ids: list[int]) -> None:
    from app.models.content import ContentPackage, ContentPackageVersion, ResourceRef
    from sqlalchemy import delete

    if not package_ids:
        return
    await db.execute(delete(ResourceRef).where(ResourceRef.package_id.in_(package_ids)))
    await db.execute(delete(ContentPackageVersion).where(ContentPackageVersion.package_id.in_(package_ids)))
    await db.execute(delete(ContentPackage).where(ContentPackage.id.in_(package_ids)))
    await db.commit()


async def _delete_files(db, file_ids: list[int]) -> None:
    from app.models.file import File
    from sqlalchemy import delete

    if not file_ids:
        return
    await db.execute(delete(File).where(File.id.in_(file_ids)))
    await db.commit()


async def _delete_artifacts(db, artifact_ids: list[int]) -> None:
    from app.models.artifact import Artifact, ArtifactOperation, ArtifactVersion
    from sqlalchemy import delete

    if not artifact_ids:
        return
    await db.execute(delete(ArtifactOperation).where(ArtifactOperation.artifact_id.in_(artifact_ids)))
    await db.execute(delete(ArtifactVersion).where(ArtifactVersion.artifact_id.in_(artifact_ids)))
    await db.execute(delete(Artifact).where(Artifact.id.in_(artifact_ids)))
    await db.commit()


async def _file_storage_paths(db, file_ids: list[int]) -> list[Path]:
    from app.config import get_settings
    from app.models.file import File

    upload_root = Path(get_settings().UPLOAD_DIR).resolve()
    paths: list[Path] = []
    for file_id in file_ids:
        file_rec = await db.get(File, file_id)
        if file_rec and file_rec.storage_path:
            paths.append(upload_root / file_rec.storage_path)
    return paths


async def _delete_resources(db, resource_ids: list[int]) -> None:
    from app.config import get_settings
    from app.models.content import Resource, ResourceRef
    from sqlalchemy import delete

    if not resource_ids:
        return
    resources = [await db.get(Resource, resource_id) for resource_id in resource_ids]
    upload_root = Path(get_settings().UPLOAD_DIR).resolve()
    await db.execute(delete(ResourceRef).where(ResourceRef.resource_id.in_(resource_ids)))
    await db.execute(delete(Resource).where(Resource.id.in_(resource_ids)))
    await db.commit()
    for resource in resources:
        if resource and resource.storage_path:
            (upload_root / resource.storage_path).unlink(missing_ok=True)


# ====================================================================
# 1. Content IR validator tests
# ====================================================================


class TestValidateIR:
    """Tests for content IR validation."""

    @pytest.mark.asyncio
    async def test_valid_document_validates_ok(self):
        result = await validate_ir(_valid_document_ir())
        assert result.valid is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_missing_required_fields(self):
        result = await validate_ir({})
        assert result.valid is False
        codes = {e.code for e in result.errors}
        assert "missing_required_field" in codes
        paths = {e.path for e in result.errors}
        assert "schema_version" in paths
        assert "content_type" in paths
        assert "title" in paths
        assert "blocks" in paths

    @pytest.mark.asyncio
    async def test_invalid_content_type(self):
        ir = _valid_document_ir(content_type="unknown_type")
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.code == "invalid_content_type" for e in result.errors)

    @pytest.mark.asyncio
    async def test_unsupported_block_type(self):
        ir = _valid_document_ir(blocks=[{"type": "textboxx", "text": "bad"}])
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.code == "unsupported_block_type" for e in result.errors)

    @pytest.mark.asyncio
    async def test_spreadsheet_top_level_non_sheet(self):
        ir = _valid_spreadsheet_ir(blocks=[{"type": "paragraph", "text": "wrong"}])
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.code == "spreadsheet_needs_sheet" for e in result.errors)

    @pytest.mark.asyncio
    async def test_spreadsheet_table_row_length_mismatch(self):
        ir = {
            "schema_version": "1.0",
            "content_type": "spreadsheet",
            "title": "Bad Sheet",
            "blocks": [
                {
                    "type": "sheet",
                    "text": "Sheet1",
                    "children": [
                        {
                            "type": "table",
                            "data": {
                                "headers": ["A", "B", "C"],
                                "rows": [["1", "2"]],
                            },
                        }
                    ],
                }
            ],
        }
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.code == "row_length_mismatch" for e in result.errors)

    @pytest.mark.asyncio
    async def test_presentation_top_level_non_slide(self):
        ir = _valid_presentation_ir(blocks=[{"type": "paragraph", "text": "wrong"}])
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.code == "presentation_needs_slide" for e in result.errors)

    @pytest.mark.asyncio
    async def test_presentation_slide_allowed_children(self):
        ir = {
            "schema_version": "1.0",
            "content_type": "presentation",
            "title": "Bad Deck",
            "blocks": [
                {
                    "type": "slide",
                    "children": [{"type": "sheet", "text": "not allowed inside slide"}],
                }
            ],
        }
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.code == "unsupported_block_in_slide" for e in result.errors)

    @pytest.mark.asyncio
    async def test_mixed_resource_ref_unresolved(self):
        ir = {
            "schema_version": "1.0",
            "content_type": "mixed",
            "title": "Mixed Doc",
            "blocks": [
                {"type": "paragraph", "text": "text", "resource_ref": "r_nonexistent"}
            ],
            "resources": [{"id": "r1", "resource_type": "image"}],
        }
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.code == "unresolved_resource_ref" for e in result.errors)

    @pytest.mark.asyncio
    async def test_memory_block_with_style(self):
        ir = {
            "schema_version": "1.0",
            "content_type": "memory",
            "title": "Memory",
            "blocks": [{"type": "paragraph", "text": "fact", "style": {"bold": True}}],
        }
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.code == "memory_no_style" for e in result.errors)

    @pytest.mark.asyncio
    async def test_image_at_least_one_block_or_resource(self):
        ir = {
            "schema_version": "1.0",
            "content_type": "image",
            "title": "Image",
            "blocks": [],
            "resources": [],
        }
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.code == "image_no_content" for e in result.errors)

    @pytest.mark.asyncio
    async def test_spreadsheet_invalid_excel_address(self):
        ir = {
            "schema_version": "1.0",
            "content_type": "spreadsheet",
            "title": "Bad Sheet",
            "blocks": [
                {
                    "type": "sheet",
                    "children": [
                        {"type": "range", "data": {"start_cell": "INVALID", "end_cell": "B10"}}
                    ],
                }
            ],
        }
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.code == "invalid_excel_address" for e in result.errors)

    def test_validate_ir_sync(self):
        """Synchronous wrapper works."""
        result = validate_ir_sync(_valid_document_ir())
        assert result.valid is True

    def test_validate_ir_sync_invalid(self):
        result = validate_ir_sync({"content_type": "bad"})
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_authoritative_fields_and_assets_alias_validate(self):
        ir = _valid_document_ir(
            source_file_id=123,
            source_module="agent",
            parser="docx-parser:parse",
            assets=[{"id": "r1", "resource_type": "image", "mime_type": "image/png"}],
            warnings=[{"code": "low_confidence", "message": "OCR was partial"}],
            quality={"confidence": 0.82},
        )
        result = await validate_ir(ir)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_authoritative_quality_must_be_object(self):
        ir = _valid_document_ir(quality="high")
        result = await validate_ir(ir)
        assert result.valid is False
        assert any(e.path == "quality" and e.code == "invalid_type" for e in result.errors)


class TestParserOutputNormalization:
    """Tests for legacy parser output -> authoritative Content IR."""

    @pytest.mark.asyncio
    async def test_legacy_document_parser_output_gets_source_trace(self):
        legacy = {
            "file_id": 101,
            "format": "pdf",
            "blocks": [
                {"type": "paragraph", "text": "Page text", "page": 3, "resource_ref": None}
            ],
            "resources": [],
        }
        ir = normalize_parser_output(legacy, module="pdf-parser", filename="sample.pdf")

        assert ir["schema_version"] == "1.0"
        assert ir["source_module"] == "pdf-parser"
        assert ir["parser"] == "pdf-parser:parse"
        assert ir["source"] == {
            "module": "pdf-parser",
            "file_id": 101,
            "filename": "sample.pdf",
            "mime_type": None,
            "format": "pdf",
        }
        assert ir["blocks"][0]["source_ref"]["page"] == 3
        result = await validate_ir(ir)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_table_parser_output_becomes_spreadsheet_ir(self):
        legacy = {
            "file_id": 102,
            "format": "csv",
            "content_type": "document",
            "title": "Legacy CSV document",
            "blocks": [
                {"type": "paragraph", "text": "表格：2列 x 1行数据", "page": None, "resource_ref": None},
                {"type": "table", "text": "A | B\n1 | 2", "page": None, "resource_ref": None},
            ],
            "resources": [],
        }
        ir = normalize_parser_output(legacy, module="csv-parser", filename="sample.csv")

        assert ir["content_type"] == "spreadsheet"
        assert ir["blocks"][0]["type"] == "sheet"
        assert ir["blocks"][0]["children"]
        assert ir["blocks"][0]["source_ref"]["sheet"] == "csv"
        result = await validate_ir(ir)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_markdown_mixed_parser_output_keeps_image_refs(self):
        legacy = {
            "schema_version": "1.0",
            "content_type": "mixed",
            "file_id": 105,
            "format": "markdown",
            "blocks": [
                {"type": "heading", "text": "Doc", "page": None, "resource_ref": None},
                {"type": "image", "text": "Chart", "page": None, "resource_ref": 1},
            ],
            "resources": [{"id": 1, "type": "image", "text_desc": "Markdown image"}],
        }
        ir = normalize_parser_output(legacy, module="markdown-parser", filename="doc.md")

        assert ir["content_type"] == "mixed"
        assert [block["type"] for block in ir["blocks"]] == ["heading", "image"]
        assert ir["blocks"][1]["source_ref"]["resource_ref"] == 1
        result = await validate_ir(ir)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_pptx_parser_output_groups_blocks_by_slide(self):
        legacy = {
            "file_id": 103,
            "format": "pptx",
            "blocks": [
                {"type": "heading", "text": "S1", "page": 1, "resource_ref": None},
                {"type": "paragraph", "text": "S2 body", "page": 2, "resource_ref": None},
            ],
            "resources": [],
        }
        ir = normalize_parser_output(legacy, module="pptx-parser", filename="deck.pptx")

        assert ir["content_type"] == "presentation"
        assert [block["source_ref"]["slide"] for block in ir["blocks"]] == [1, 2]
        assert ir["blocks"][0]["children"][0]["source_ref"]["page"] == 1
        result = await validate_ir(ir)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_image_vision_output_preserves_resource_evidence(self):
        legacy = {
            "file_id": 104,
            "format": "png",
            "description": "A chart image",
            "blocks": [
                {"type": "image", "text": "A chart image", "page": None, "resource_ref": 1}
            ],
            "resources": [
                {
                    "id": 1,
                    "type": "image",
                    "file_storage_id": 104,
                    "text_desc": "A chart image",
                    "metadata": {"width": 640, "height": 480},
                }
            ],
        }
        ir = normalize_parser_output(legacy, module="image-vision", filename="chart.png")

        assert ir["content_type"] == "image"
        assert ir["blocks"][0]["source_ref"]["resource_ref"] == 1
        assert ir["resources"][0]["resource_type"] == "image"
        assert ir["resources"][0]["description"] == "A chart image"
        result = await validate_ir(ir)
        assert result.valid is True


# ====================================================================
# 2. Content IR writer tests
# ====================================================================


class TestWriteIR:
    """Tests for content IR writer. Mocks DB and cross-module calls."""

    @pytest.mark.asyncio
    async def test_invalid_ir_raises_structured_error(self):
        """Invalid IR raises AppValidationError with structured details."""
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            with pytest.raises(AppValidationError) as exc_info:
                await write_ir(
                    db,
                    {"schema_version": "1.0", "content_type": "document", "title": "bad", "blocks": [{"type": "textboxx", "text": "bad"}]},
                    owner_id=1,
                    caller="user:1",
                )
            assert exc_info.value.details is not None
            assert len(exc_info.value.details) > 0
            assert any(d.get("code") == "unsupported_block_type" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_document_write_creates_package(self):
        """Valid document IR creates ContentPackage + version."""
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage, ContentPackageVersion

        owner_id = 9991
        async with AsyncSessionLocal() as db:
            try:
                result = await write_ir(
                    db, _valid_document_ir(),
                    owner_id=owner_id,
                    caller=f"user:{owner_id}",
                )
                assert result["canonical_source"] == "content_package"
                assert result["owner_id"] == owner_id
                assert result["package_id"] > 0
                assert result["version_id"] > 0
                assert result["version_no"] >= 1

                # Verify DB records
                pkg = await db.get(ContentPackage, result["package_id"])
                assert pkg is not None
                assert pkg.owner_id == owner_id
                assert pkg.package_type == "document"

                ver = await db.get(ContentPackageVersion, result["version_id"])
                assert ver is not None
                assert ver.package_id == pkg.id

                # Cleanup
                await _delete_content_packages(db, [result["package_id"]])
            except Exception:
                await db.rollback()
                raise

    @pytest.mark.asyncio
    async def test_write_ir_persists_authoritative_metadata(self):
        """ContentPackage version keeps source/parser/assets/warnings/quality in canonical DB JSON."""
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackageVersion

        owner_id = 99910
        raw_resource = b"content-ir-authority-" + uuid.uuid4().bytes
        ir = _valid_document_ir(
            source_module="agent",
            parser="markdown-parser:parse",
            metadata={"workflow_id": "wf-test"},
            warnings=[{"code": "truncated", "message": "sample"}],
            quality={"confidence": 0.91},
            assets=[{
                "id": "asset-1",
                "resource_type": "image",
                "mime_type": "image/png",
                "filename": "asset.png",
                "data_b64": base64.b64encode(raw_resource).decode("ascii"),
            }],
        )
        async with AsyncSessionLocal() as db:
            resource_id = None
            try:
                result = await write_ir(
                    db,
                    ir,
                    owner_id=owner_id,
                    caller=f"user:{owner_id}",
                )
                version = await db.get(ContentPackageVersion, result["version_id"])
                assert version is not None
                content = json.loads(version.content_json)
                resource_id = content["resources"][0]["resource_id"]
                assert content["manifest"]["source_module"] == "agent"
                assert content["manifest"]["parser"] == "markdown-parser:parse"
                assert content["metadata"] == {"workflow_id": "wf-test"}
                assert content["warnings"][0]["code"] == "truncated"
                assert content["quality"]["confidence"] == 0.91
                assert content["assets"][0]["resource_id"] == resource_id
            finally:
                if "result" in locals():
                    await _delete_content_packages(db, [result["package_id"]])
                if resource_id is not None:
                    await _delete_resources(db, [resource_id])

    @pytest.mark.asyncio
    async def test_write_ir_source_file_id_requires_file_access(self):
        """content:write_ir must not let a caller update another user's file package by ID."""
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage
        from app.models.file import File
        from app.routers.content import _cap_write_ir
        from sqlalchemy import select

        owner_id = 4
        intruder_id = 5
        file_id = None
        package_ids: list[int] = []
        async with AsyncSessionLocal() as db:
            file_rec = File(
                name=f"content-ir-security-{uuid.uuid4().hex}",
                extension="txt",
                size=0,
                owner_id=owner_id,
                storage_path="content-ir-security-test.txt",
                mime_type="text/plain",
                deleted=False,
            )
            db.add(file_rec)
            await db.commit()
            await db.refresh(file_rec)
            file_id = file_rec.id

        try:
            result = await _cap_write_ir(
                {
                    "content_ir": _valid_document_ir(title="Unauthorized write"),
                    "source_file_id": file_id,
                },
                caller=f"user:{intruder_id}",
            )
            assert result["success"] is False
            assert "Permission denied" in result.get("error", "")

            async with AsyncSessionLocal() as db:
                existing = await db.execute(
                    select(ContentPackage).where(ContentPackage.source_file_id == file_id)
                )
                packages = existing.scalars().all()
                package_ids = [pkg.id for pkg in packages]
                assert packages == []
        finally:
            async with AsyncSessionLocal() as db:
                await _delete_content_packages(db, package_ids)
                if file_id is not None:
                    await _delete_files(db, [file_id])

    @pytest.mark.asyncio
    async def test_write_ir_requires_edit_share_and_preserves_source_owner(self):
        """Read shares cannot write IR; edit shares write into the source owner's package."""
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage
        from app.models.file import File
        from app.models.file_share import FileShare
        from app.routers.content import _cap_write_ir
        from sqlalchemy import delete, select

        owner_id = 4
        shared_user_id = 2
        file_id = None
        package_ids: list[int] = []
        async with AsyncSessionLocal() as db:
            file_rec = File(
                name=f"content-ir-edit-share-{uuid.uuid4().hex}",
                extension="txt",
                size=0,
                owner_id=owner_id,
                storage_path="content-ir-edit-share-test.txt",
                mime_type="text/plain",
                deleted=False,
            )
            db.add(file_rec)
            await db.flush()
            share = FileShare(
                file_id=file_rec.id,
                shared_by_owner_id=owner_id,
                shared_with_user_id=shared_user_id,
                permission="read",
            )
            db.add(share)
            await db.commit()
            file_id = file_rec.id

        try:
            read_result = await _cap_write_ir(
                {
                    "content_ir": _valid_document_ir(title="Read share denied"),
                    "source_file_id": file_id,
                },
                caller=f"user:{shared_user_id}",
            )
            assert read_result["success"] is False
            assert "Edit permission required" in read_result.get("error", "")

            async with AsyncSessionLocal() as db:
                share = await db.scalar(
                    select(FileShare).where(
                        FileShare.file_id == file_id,
                        FileShare.shared_with_user_id == shared_user_id,
                    )
                )
                assert share is not None
                share.permission = "edit"
                await db.commit()

            edit_result = await _cap_write_ir(
                {
                    "content_ir": _valid_document_ir(title="Edit share allowed"),
                    "source_file_id": file_id,
                },
                caller=f"user:{shared_user_id}",
            )
            assert edit_result["success"] is True
            package_id = edit_result["data"]["package_id"]
            package_ids.append(package_id)
            assert edit_result["data"]["owner_id"] == owner_id
            assert edit_result["data"]["written_by"] == shared_user_id

            async with AsyncSessionLocal() as db:
                pkg = await db.get(ContentPackage, package_id)
                assert pkg is not None
                assert pkg.owner_id == owner_id
                assert pkg.source_file_id == file_id
        finally:
            async with AsyncSessionLocal() as db:
                await _delete_content_packages(db, package_ids)
                if file_id is not None:
                    await db.execute(delete(FileShare).where(FileShare.file_id == file_id))
                    await db.commit()
                    await _delete_files(db, [file_id])

    @pytest.mark.asyncio
    async def test_mixed_write_preserves_resources_and_refs(self):
        """ContentPackage writes keep IR resources and persist ResourceRef links."""
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackageVersion, ResourceRef
        from sqlalchemy import select

        owner_id = 4
        package_id = None
        resource_id = None
        raw_resource = b"content-ir-resource-" + uuid.uuid4().bytes
        ir = {
            "schema_version": "1.0",
            "content_type": "mixed",
            "title": "Mixed Resource Doc",
            "blocks": [
                {
                    "id": "img-block",
                    "type": "image",
                    "text": "Diagram",
                    "resource_ref": "r1",
                }
            ],
            "resources": [
                {
                    "id": "r1",
                    "resource_type": "image",
                    "mime_type": "image/png",
                    "filename": "diagram.png",
                    "description": "embedded diagram",
                    "data_b64": base64.b64encode(raw_resource).decode("ascii"),
                }
            ],
        }

        async with AsyncSessionLocal() as db:
            try:
                result = await write_ir(
                    db,
                    ir,
                    owner_id=owner_id,
                    caller=f"user:{owner_id}",
                )
                package_id = result["package_id"]
                version = await db.get(ContentPackageVersion, result["version_id"])
                assert version is not None
                content = json.loads(version.content_json)

                assert "resources" in content
                assert content["resources"][0]["id"] == "r1"
                assert "data_b64" not in content["resources"][0]
                resource_id = content["resources"][0]["resource_id"]
                assert resource_id > 0
                assert content["blocks"][0]["resource_ref"] == resource_id

                refs = await db.execute(
                    select(ResourceRef).where(ResourceRef.package_id == package_id)
                )
                ref_rows = refs.scalars().all()
                assert len(ref_rows) == 1
                assert ref_rows[0].resource_id == resource_id
                assert ref_rows[0].block_id == "img-block"
                assert ref_rows[0].version_id == result["version_id"]
            finally:
                if package_id is not None:
                    await _delete_content_packages(db, [package_id])
                if resource_id is not None:
                    await _delete_resources(db, [resource_id])

    @pytest.mark.asyncio
    async def test_consecutive_writes_different_packages(self):
        """Two writes without source_file_id create different packages."""
        from app.database import AsyncSessionLocal

        owner_id = 9992
        async with AsyncSessionLocal() as db:
            try:
                r1 = await write_ir(
                    db, _valid_document_ir(title="Doc A"),
                    owner_id=owner_id, caller=f"user:{owner_id}",
                )
                r2 = await write_ir(
                    db, _valid_document_ir(title="Doc B"),
                    owner_id=owner_id, caller=f"user:{owner_id}",
                )
                assert r1["package_id"] != r2["package_id"]

                # Cleanup
                await _delete_content_packages(db, [r1["package_id"], r2["package_id"]])
            except Exception:
                await db.rollback()
                raise

    @pytest.mark.asyncio
    async def test_spreadsheet_write_passes_headers_to_excel(self):
        """Spreadsheet write should include headers + rows in update_range call."""
        ir = _valid_spreadsheet_ir()
        owner_id = 9993

        with mock.patch("app.services.content.ir_writer.call_capability") as mock_cc:
            mock_cc.return_value = {"state_key": "test_wb_1"}

            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                try:
                    result = await write_ir(
                        db, ir,
                        owner_id=owner_id,
                        caller=f"user:{owner_id}",
                    )
                    assert result["canonical_source"] == "excel_engine"
                    # Verify update_range was called with headers + rows
                    update_calls = [
                        c for c in mock_cc.call_args_list
                        if c[0][1] == "update_range"
                    ]
                    assert len(update_calls) > 0
                    args = update_calls[-1][0]
                    # args[0]=module, args[1]=action, args[2]=params, args[3]=caller
                    params = args[2]
                    assert params["rows"] == [["日期", "产品"], ["2026-07-01", "A"]]
                    assert params["start_row"] == 0
                    assert params["start_col"] == 0
                except Exception:
                    await db.rollback()
                    raise

    @pytest.mark.asyncio
    async def test_spreadsheet_write_parses_start_cell(self):
        """start_cell=A5: C5 should become start_row=4, start_col=2."""
        ir = _valid_spreadsheet_ir()
        ir["blocks"][0]["children"][0]["data"]["start_cell"] = "C5"

        with mock.patch("app.services.content.ir_writer.call_capability") as mock_cc:
            mock_cc.return_value = {"state_key": "test_wb_2"}
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                try:
                    await write_ir(
                        db, ir, owner_id=9994, caller="user:9994",
                    )
                    update_calls = [
                        c for c in mock_cc.call_args_list
                        if c[0][1] == "update_range"
                    ]
                    assert len(update_calls) > 0
                    args = update_calls[-1][0]
                    params = args[2]
                    assert params["start_row"] == 4  # 0-based, row 5
                    assert params["start_col"] == 2  # 0-based, col C
                except Exception:
                    await db.rollback()
                    raise

    @pytest.mark.asyncio
    async def test_image_write_returns_resource_ids(self):
        """Image write should return non-empty resource_ids list."""
        ir = {
            "schema_version": "1.0",
            "content_type": "image",
            "title": "Test Image",
            "blocks": [{"type": "image", "text": "desc", "resource_ref": "r1"}],
            "resources": [{"id": "r1", "resource_type": "image", "data_b64": "AAAA"}],
        }
        from app.database import AsyncSessionLocal

        with mock.patch("app.services.content.ir_writer.call_capability") as mock_cc:
            mock_cc.return_value = {"id": 100, "state_key": "test"}
            async with AsyncSessionLocal() as db:
                result = await write_ir(
                    db, ir, owner_id=9995, caller="user:9995",
                )
                assert result["canonical_source"] == "resource"
                # store_resource should have been called at least once
                store_calls = [
                    c for c in mock_cc.call_args_list
                    if c[0][1] == "store_resource"
                ]
                assert len(store_calls) >= 1

    @pytest.mark.asyncio
    async def test_store_resource_requires_file_access_before_persist(self):
        """store_resource(file_id=...) must fail before creating a resource for inaccessible files."""
        from app.database import AsyncSessionLocal
        from app.models.content import Resource
        from app.models.file import File
        from app.routers.content import _cap_store_resource
        from sqlalchemy import select

        owner_id = 4
        intruder_id = 5
        file_id = None
        raw_resource = b"content-ir-denied-resource-" + uuid.uuid4().bytes
        resource_hash = hashlib.sha256(raw_resource).hexdigest()
        data_b64 = base64.b64encode(raw_resource).decode("ascii")

        async with AsyncSessionLocal() as db:
            file_rec = File(
                name=f"content-ir-resource-denied-{uuid.uuid4().hex}",
                extension="txt",
                size=0,
                owner_id=owner_id,
                storage_path="content-ir-resource-denied.txt",
                mime_type="text/plain",
                deleted=False,
            )
            db.add(file_rec)
            await db.commit()
            await db.refresh(file_rec)
            file_id = file_rec.id

        try:
            result = await _cap_store_resource(
                {
                    "data_b64": data_b64,
                    "resource_type": "image",
                    "mime_type": "image/png",
                    "filename": "denied.png",
                    "file_id": file_id,
                },
                caller=f"user:{intruder_id}",
            )
            assert result["success"] is False
            assert "Permission denied" in result.get("error", "")

            async with AsyncSessionLocal() as db:
                existing = await db.execute(
                    select(Resource).where(Resource.hash == resource_hash)
                )
                assert existing.scalar_one_or_none() is None
        finally:
            async with AsyncSessionLocal() as db:
                if file_id is not None:
                    await _delete_files(db, [file_id])

    @pytest.mark.asyncio
    async def test_version_conflict_detected(self):
        """expected_version_id mismatch should raise ConflictError."""
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage
        from sqlalchemy import select

        owner_id = 9996
        async with AsyncSessionLocal() as db:
            try:
                r1 = await write_ir(
                    db, _valid_document_ir(),
                    owner_id=owner_id, caller=f"user:{owner_id}",
                )
                wrong_version = (r1["version_id"] or 0) + 99999
                with pytest.raises(ConflictError):
                    await write_ir(
                        db, _valid_document_ir(),
                        owner_id=owner_id,
                        caller=f"user:{owner_id}",
                        source_file_id=r1.get("source_file_id"),
                        expected_version_id=wrong_version,
                    )
                # Cleanup
                await _delete_content_packages(db, [r1["package_id"]])
            except Exception:
                await db.rollback()
                raise
            finally:
                leftovers = await db.execute(
                    select(ContentPackage.id).where(
                        ContentPackage.owner_id == owner_id,
                        ContentPackage.source_file_id.is_(None),
                    )
                )
                await _delete_content_packages(db, list(leftovers.scalars().all()))


# ====================================================================
# 3. Compile / download tests
# ====================================================================


class TestCompileDownload:
    """Tests for content compile and download."""

    @pytest.mark.asyncio
    async def test_content_compile_no_file_record(self):
        """content:compile should NOT create framework_file_items."""
        from app.database import AsyncSessionLocal
        from app.models.file import File
        from app.routers.content import _cap_compile
        from sqlalchemy import func, select

        owner_id = 9997
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".docx")
        os.close(tmp_fd)
        Path(tmp_path).write_bytes(b"compiled")
        async with AsyncSessionLocal() as db:
            result = await write_ir(
                db,
                _valid_document_ir(title="Compile Test"),
                owner_id=owner_id,
                caller=f"user:{owner_id}",
            )
            package_id = result["package_id"]
            before = (await db.execute(select(func.count()).select_from(File))).scalar_one()

        try:
            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file"
            ) as mock_compile:
                mock_compile.return_value = (Path(tmp_path), "test.docx")
                compiled = await _cap_compile(
                    {"package_id": package_id, "target_format": "docx"},
                    f"user:{owner_id}",
                )
            assert compiled["success"] is True
            assert compiled["data"]["filename"] == "test.docx"

            async with AsyncSessionLocal() as db:
                after = (await db.execute(select(func.count()).select_from(File))).scalar_one()
                assert after == before
        finally:
            async with AsyncSessionLocal() as db:
                await _delete_content_packages(db, [package_id])
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_compile_path_security_rejects_invalid_path(self):
        """Compile with invalid temp path should fail security."""
        from app.database import AsyncSessionLocal
        from app.routers.content import _cap_compile

        owner_id = 9998
        invalid_path = Path(__file__).resolve()
        async with AsyncSessionLocal() as db:
            result = await write_ir(
                db,
                _valid_document_ir(title="Invalid Path Compile Test"),
                owner_id=owner_id,
                caller=f"user:{owner_id}",
            )
            package_id = result["package_id"]

        try:
            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file"
            ) as mock_compile:
                mock_compile.return_value = (invalid_path, "test.docx")
                compiled = await _cap_compile(
                    {"package_id": package_id, "target_format": "docx"},
                    f"user:{owner_id}",
                )
            assert compiled == {"success": False, "error": "Invalid compile output path"}
        finally:
            async with AsyncSessionLocal() as db:
                await _delete_content_packages(db, [package_id])

    @pytest.mark.asyncio
    async def test_compile_rejects_filename_with_path_sep(self):
        """Filenames with / or \\ should be rejected."""
        from app.database import AsyncSessionLocal
        from app.routers.content import _cap_compile

        owner_id = 9999
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".docx")
        os.close(tmp_fd)
        Path(tmp_path).write_bytes(b"compiled")
        async with AsyncSessionLocal() as db:
            result = await write_ir(
                db,
                _valid_document_ir(title="Bad Filename Compile Test"),
                owner_id=owner_id,
                caller=f"user:{owner_id}",
            )
            package_id = result["package_id"]

        try:
            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file"
            ) as mock_compile:
                mock_compile.return_value = (Path(tmp_path), "../bad.docx")
                compiled = await _cap_compile(
                    {"package_id": package_id, "target_format": "docx"},
                    f"user:{owner_id}",
                )
            assert compiled == {"success": False, "error": "Invalid filename"}
        finally:
            async with AsyncSessionLocal() as db:
                await _delete_content_packages(db, [package_id])
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_excel_compile_nonexistent_workbook_fails(self):
        """excel-engine:compile_xlsx with missing state_key should fail."""
        from app.services.module_registry import call_capability

        result = await call_capability(
            "excel-engine", "compile_xlsx",
            {"state_key": "__test_nonexistent_workbook__"},
            caller="user:4",
            caller_role="viewer",
        )
        data = result.get("data", result) if isinstance(result, dict) else {}
        assert data.get("success") is False
        assert "Workbook not found" in data.get("error", "")

    @pytest.mark.asyncio
    async def test_spreadsheet_package_skipped_in_compile(self):
        """Spreadsheet ContentPackages should be skipped in download compile."""
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage, ContentPackageVersion
        from app.models.file import File
        from app.routers.file_transfer import _try_compile_from_content_package

        owner_id = 4
        async with AsyncSessionLocal() as db:
            file_rec = File(
                name="spreadsheet-source",
                extension="xlsx",
                size=0,
                owner_id=owner_id,
                storage_path="missing.xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                deleted=False,
            )
            db.add(file_rec)
            await db.flush()
            pkg = ContentPackage(
                owner_id=owner_id,
                source_file_id=file_rec.id,
                package_type="spreadsheet",
                origin_type="generated",
                source_extension="xlsx",
                status="parsed",
            )
            db.add(pkg)
            await db.flush()
            version = ContentPackageVersion(
                package_id=pkg.id,
                version_no=1,
                content_json=json.dumps({"manifest": {}, "blocks": []}),
                operation_type="write_ir",
                created_by=owner_id,
            )
            db.add(version)
            await db.flush()
            pkg.current_version_id = version.id
            await db.commit()
            file_id = file_rec.id
            package_id = pkg.id

        try:
            with mock.patch("app.routers.file_transfer.call_capability") as mock_call:
                async with AsyncSessionLocal() as db:
                    result = await _try_compile_from_content_package(db, file_id, owner_id)
            assert result is None
            mock_call.assert_not_called()
        finally:
            async with AsyncSessionLocal() as cleanup_db:
                await _delete_content_packages(cleanup_db, [package_id])
                file_to_delete = await cleanup_db.get(File, file_id)
                if file_to_delete:
                    await cleanup_db.delete(file_to_delete)
                    await cleanup_db.commit()

    @pytest.mark.asyncio
    async def test_degraded_package_is_used_for_download_compile(self):
        """Degraded ContentPackages still contain usable body text and should compile."""
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage, ContentPackageVersion
        from app.models.file import File
        from app.routers.file_transfer import _try_compile_from_content_package

        owner_id = 4
        async with AsyncSessionLocal() as db:
            file_rec = File(
                name=f"degraded-download-{uuid.uuid4().hex}",
                extension="docx",
                size=0,
                owner_id=owner_id,
                storage_path="missing-degraded-download.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                deleted=False,
            )
            db.add(file_rec)
            await db.flush()
            pkg = ContentPackage(
                owner_id=owner_id,
                source_file_id=file_rec.id,
                package_type="document",
                origin_type="generated",
                source_extension="docx",
                status="degraded",
            )
            db.add(pkg)
            await db.flush()
            version = ContentPackageVersion(
                package_id=pkg.id,
                version_no=1,
                content_json=json.dumps({
                    "manifest": {"title": file_rec.name},
                    "blocks": [{"id": "b1", "type": "paragraph", "text": "kept body"}],
                    "parse_status": "degraded",
                }, ensure_ascii=False),
                operation_type="parse",
                created_by=owner_id,
            )
            db.add(version)
            await db.flush()
            pkg.current_version_id = version.id
            await db.commit()
            file_id = file_rec.id
            package_id = pkg.id

        try:
            compile_payload = {
                "success": True,
                "data": {
                    "file_path": "/tmp/degraded-download.docx",
                    "filename": "degraded-download.docx",
                },
            }
            with mock.patch(
                "app.routers.file_transfer.call_capability",
                new=mock.AsyncMock(return_value=compile_payload),
            ) as mock_call:
                async with AsyncSessionLocal() as db:
                    result = await _try_compile_from_content_package(db, file_id, owner_id)

            assert result == {
                "file_path": "/tmp/degraded-download.docx",
                "filename": "degraded-download.docx",
            }
            mock_call.assert_awaited_once()
            assert mock_call.await_args.args[:2] == ("content", "compile")
            assert mock_call.await_args.args[2]["package_id"] == package_id
        finally:
            async with AsyncSessionLocal() as cleanup_db:
                await _delete_content_packages(cleanup_db, [package_id])
                await _delete_files(cleanup_db, [file_id])


class TestContentPublishTarget:
    """Tests for publishing ContentPackages to desktop artifacts/files."""

    @pytest.mark.asyncio
    async def test_publish_with_target_file_replaces_target_without_new_file(self):
        """target_file_id should replace the target file instead of creating a new one."""
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage
        from app.models.file import File
        from app.services.content.export_service import ContentExportService
        from sqlalchemy import func, select

        owner_id = 4
        target_file_id: int | None = None
        package_id: int | None = None
        artifact_ids: list[int] = []
        cleanup_file_ids: list[int] = []
        cleanup_paths: list[Path] = []
        new_content = b"published target content"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt")
        os.close(tmp_fd)
        Path(tmp_path).write_bytes(new_content)

        async with AsyncSessionLocal() as db:
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
            cleanup_file_ids.append(target_file_id)

            write_result = await write_ir(
                db,
                _valid_document_ir(title="Publish Target Test"),
                owner_id=owner_id,
                caller=f"user:{owner_id}",
            )
            package_id = write_result["package_id"]
            package = await db.get(ContentPackage, package_id)
            assert package is not None
            package.source_extension = "txt"
            await db.commit()
            before_files = (await db.execute(select(func.count()).select_from(File))).scalar_one()

            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file"
            ) as mock_compile:
                mock_compile.return_value = (Path(tmp_path), "compiled.txt")
                published = await ContentExportService().publish(
                    db,
                    package_id,
                    target_file_id=target_file_id,
                    owner_id=owner_id,
                )

            after_files = (await db.execute(select(func.count()).select_from(File))).scalar_one()
            refreshed = await db.get(File, target_file_id)
            assert refreshed is not None
            cleanup_paths.extend(await _file_storage_paths(db, cleanup_file_ids))

        try:
            assert published["status"] == "replaced"
            assert published["file_id"] == target_file_id
            assert published["target_file_id"] == target_file_id
            assert published["artifact"]["file_id"] == target_file_id
            artifact_ids.append(published["artifact"]["id"])
            assert after_files == before_files
            assert refreshed.size == len(new_content)
            assert refreshed.md5_hash == hashlib.md5(new_content).hexdigest()
            assert cleanup_paths
            assert cleanup_paths[-1].read_bytes() == new_content
        finally:
            async with AsyncSessionLocal() as db:
                await _delete_artifacts(db, artifact_ids)
                if package_id is not None:
                    await _delete_content_packages(db, [package_id])
                cleanup_paths.extend(await _file_storage_paths(db, cleanup_file_ids))
                await _delete_files(db, cleanup_file_ids)
            for path in set(cleanup_paths):
                path.unlink(missing_ok=True)
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_publish_target_without_write_access_fails_without_new_file(self):
        """A target owned by another user should fail before any publish file is created."""
        from app.core.exceptions import PermissionDenied
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage
        from app.models.file import File
        from app.services.content.export_service import ContentExportService
        from sqlalchemy import func, select

        owner_id = 4
        other_owner_id = 5
        target_file_id: int | None = None
        package_id: int | None = None
        cleanup_file_ids: list[int] = []

        async with AsyncSessionLocal() as db:
            target = File(
                name=f"content-publish-denied-{uuid.uuid4().hex}",
                extension="txt",
                size=3,
                owner_id=other_owner_id,
                storage_path=f"test/missing-{uuid.uuid4().hex}.txt",
                mime_type="text/plain",
                md5_hash=hashlib.md5(b"old").hexdigest(),
                deleted=False,
            )
            db.add(target)
            await db.commit()
            await db.refresh(target)
            target_file_id = target.id
            cleanup_file_ids.append(target_file_id)

            write_result = await write_ir(
                db,
                _valid_document_ir(title="Publish Target Denied Test"),
                owner_id=owner_id,
                caller=f"user:{owner_id}",
            )
            package_id = write_result["package_id"]
            package = await db.get(ContentPackage, package_id)
            assert package is not None
            package.source_extension = "txt"
            await db.commit()
            before_files = (await db.execute(select(func.count()).select_from(File))).scalar_one()

            with pytest.raises(PermissionDenied):
                await ContentExportService().publish(
                    db,
                    package_id,
                    target_file_id=target_file_id,
                    owner_id=owner_id,
                )

            after_files = (await db.execute(select(func.count()).select_from(File))).scalar_one()

        try:
            assert after_files == before_files
        finally:
            async with AsyncSessionLocal() as db:
                if package_id is not None:
                    await _delete_content_packages(db, [package_id])
                await _delete_files(db, cleanup_file_ids)

    @pytest.mark.asyncio
    async def test_publish_without_target_keeps_create_file_behavior(self):
        """No target_file_id should keep the existing create-new-file publish path."""
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage
        from app.models.file import File
        from app.services.content.export_service import ContentExportService
        from sqlalchemy import func, select

        owner_id = 4
        package_id: int | None = None
        artifact_ids: list[int] = []
        cleanup_file_ids: list[int] = []
        cleanup_paths: list[Path] = []
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt")
        os.close(tmp_fd)
        Path(tmp_path).write_bytes(b"new publish file")

        async with AsyncSessionLocal() as db:
            write_result = await write_ir(
                db,
                _valid_document_ir(title=f"Publish New File {uuid.uuid4().hex}"),
                owner_id=owner_id,
                caller=f"user:{owner_id}",
            )
            package_id = write_result["package_id"]
            package = await db.get(ContentPackage, package_id)
            assert package is not None
            package.source_extension = "txt"
            await db.commit()
            before_files = (await db.execute(select(func.count()).select_from(File))).scalar_one()

            with mock.patch(
                "app.services.content.export_service.ContentExportService._compile_to_file"
            ) as mock_compile:
                mock_compile.return_value = (Path(tmp_path), f"created-{uuid.uuid4().hex}.txt")
                published = await ContentExportService().publish(
                    db,
                    package_id,
                    owner_id=owner_id,
                )

            cleanup_file_ids.append(published["file_id"])
            cleanup_paths.extend(await _file_storage_paths(db, cleanup_file_ids))
            after_files = (await db.execute(select(func.count()).select_from(File))).scalar_one()

        try:
            artifact_ids.append(published["artifact"]["id"])
            assert published["file_id"] != 0
            assert published["artifact"]["file_id"] == published["file_id"]
            assert after_files == before_files + 1
        finally:
            async with AsyncSessionLocal() as db:
                await _delete_artifacts(db, artifact_ids)
                if package_id is not None:
                    await _delete_content_packages(db, [package_id])
                cleanup_paths.extend(await _file_storage_paths(db, cleanup_file_ids))
                await _delete_files(db, cleanup_file_ids)
            for path in set(cleanup_paths):
                path.unlink(missing_ok=True)
            Path(tmp_path).unlink(missing_ok=True)


# ====================================================================
# 4. Content capability failure semantics
# ====================================================================


class TestContentFailureSemantics:
    """Content capabilities must not wrap parser failures as successful empty content."""

    @pytest.mark.asyncio
    async def test_pipeline_checks_caller_access_before_get_or_create(self):
        from app.core.exceptions import PermissionDenied
        from app.database import AsyncSessionLocal
        from app.models.file import File
        from app.services.content.pipeline_service import ContentPipelineService

        owner_id = 5
        caller_id = 4
        file_id = None
        async with AsyncSessionLocal() as db:
            file_rec = File(
                name=f"pipeline-access-denied-{uuid.uuid4().hex}.txt",
                extension="txt",
                size=0,
                owner_id=owner_id,
                storage_path="content-pipeline-access-denied-test.txt",
                mime_type="text/plain",
                deleted=False,
            )
            db.add(file_rec)
            await db.commit()
            await db.refresh(file_rec)
            file_id = file_rec.id

        try:
            with pytest.raises(PermissionDenied):
                await ContentPipelineService().run_pipeline(file_id, f"user:{caller_id}")
        finally:
            async with AsyncSessionLocal() as db:
                if file_id is not None:
                    await _delete_files(db, [file_id])

    @pytest.mark.asyncio
    async def test_pipeline_capability_propagates_failed_result(self):
        from app.routers import content

        with mock.patch.object(
            content.pipeline_svc,
            "run_pipeline",
            return_value={"status": "failed", "error": "pipeline failed"},
        ):
            result = await content._cap_pipeline({"file_id": 123}, "user:4")

        assert result["success"] is False
        assert result["error"] == "pipeline failed"
        assert result["data"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_pipeline_rest_propagates_failed_result(self):
        from app.core.exceptions import AppException as CoreAppException
        from app.routers import content

        user = mock.Mock()
        user.id = 4
        with mock.patch.object(
            content.pipeline_svc,
            "run_pipeline",
            return_value={"status": "failed", "error": "pipeline failed"},
        ):
            with pytest.raises(CoreAppException) as exc_info:
                await content.trigger_pipeline(content.PipelineRequest(file_id=123), user=user)

        assert "Pipeline failed: pipeline failed" in str(exc_info.value)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_get_file_content_lazy_parse_exception_fails(self):
        from app.database import AsyncSessionLocal
        from app.models.file import File
        from app.routers.content import _cap_get_file_content

        owner_id = 4
        file_id = None
        async with AsyncSessionLocal() as db:
            file_rec = File(
                name=f"lazy-parse-failure-{uuid.uuid4().hex}.txt",
                extension="txt",
                size=0,
                owner_id=owner_id,
                storage_path="content-lazy-parse-failure-test.txt",
                mime_type="text/plain",
                deleted=False,
            )
            db.add(file_rec)
            await db.commit()
            await db.refresh(file_rec)
            file_id = file_rec.id

        try:
            with (
                mock.patch(
                    "app.services.content.package_service.ContentPackageService.get_package",
                    return_value=None,
                ),
                mock.patch(
                    "app.services.content.pipeline_service.ContentPipelineService.run_pipeline",
                    side_effect=RuntimeError("parser exploded"),
                ),
            ):
                result = await _cap_get_file_content({"file_id": file_id}, f"user:{owner_id}")

            assert result["success"] is False
            assert result["error"] == "parser exploded"
            assert result["data"]["status"] == "parse_failed"
            assert "blocks" not in result["data"]
        finally:
            async with AsyncSessionLocal() as db:
                if file_id is not None:
                    await _delete_files(db, [file_id])

    @pytest.mark.asyncio
    async def test_get_file_content_skipped_parse_fails_closed(self):
        from app.database import AsyncSessionLocal
        from app.models.file import File
        from app.routers.content import _cap_get_file_content

        owner_id = 4
        file_id = None
        async with AsyncSessionLocal() as db:
            file_rec = File(
                name=f"lazy-parse-skipped-{uuid.uuid4().hex}.zip",
                extension="zip",
                size=0,
                owner_id=owner_id,
                storage_path="content-lazy-parse-skipped-test.zip",
                mime_type="application/zip",
                deleted=False,
            )
            db.add(file_rec)
            await db.commit()
            await db.refresh(file_rec)
            file_id = file_rec.id

        try:
            result = await _cap_get_file_content({"file_id": file_id}, f"user:{owner_id}")

            assert result["success"] is False
            assert "Unsupported format" in result["error"]
            assert result["data"]["status"] == "skipped"
            assert "blocks" not in result["data"]
        finally:
            async with AsyncSessionLocal() as db:
                if file_id is not None:
                    await _delete_files(db, [file_id])

    @pytest.mark.asyncio
    async def test_get_file_content_non_consumable_package_fails_closed(self):
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage
        from app.models.file import File
        from app.routers.content import _cap_get_file_content

        owner_id = 4
        file_id = None
        package_id = None
        async with AsyncSessionLocal() as db:
            file_rec = File(
                name=f"non-consumable-package-{uuid.uuid4().hex}.txt",
                extension="txt",
                size=0,
                owner_id=owner_id,
                storage_path="content-non-consumable-package-test.txt",
                mime_type="text/plain",
                deleted=False,
            )
            db.add(file_rec)
            await db.flush()
            pkg = ContentPackage(
                owner_id=owner_id,
                source_file_id=file_rec.id,
                package_type="text",
                origin_type="uploaded",
                source_extension="txt",
                status="pending",
            )
            db.add(pkg)
            await db.commit()
            file_id = file_rec.id
            package_id = pkg.id

        try:
            with mock.patch(
                "app.services.content.pipeline_service.ContentPipelineService.run_pipeline",
                return_value={"package_id": package_id, "status": "pending"},
            ):
                result = await _cap_get_file_content({"file_id": file_id}, f"user:{owner_id}")

            assert result["success"] is False
            assert result["data"]["source"] == "content_package"
            assert result["data"]["status"] == "pending"
            assert result["data"]["package_id"] == package_id
            assert "blocks" not in result["data"]
        finally:
            async with AsyncSessionLocal() as db:
                if package_id is not None:
                    await _delete_content_packages(db, [package_id])
                if file_id is not None:
                    await _delete_files(db, [file_id])

    @pytest.mark.asyncio
    async def test_get_file_content_empty_consumable_package_fails_closed(self):
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage, ContentPackageVersion
        from app.models.file import File
        from app.routers.content import _cap_get_file_content

        owner_id = 4
        async with AsyncSessionLocal() as db:
            file_rec = File(
                name=f"empty-parsed-package-{uuid.uuid4().hex}.txt",
                extension="txt",
                size=0,
                owner_id=owner_id,
                storage_path="content-empty-parsed-package-test.txt",
                mime_type="text/plain",
                deleted=False,
            )
            db.add(file_rec)
            await db.flush()
            pkg = ContentPackage(
                owner_id=owner_id,
                source_file_id=file_rec.id,
                package_type="text",
                origin_type="uploaded",
                source_extension="txt",
                status="parsed",
                manifest_json=json.dumps({"title": file_rec.name}, ensure_ascii=False),
            )
            db.add(pkg)
            await db.flush()
            version = ContentPackageVersion(
                package_id=pkg.id,
                version_no=1,
                content_json=json.dumps({"manifest": {"title": file_rec.name}, "blocks": []}),
                operation_type="parse",
                created_by=owner_id,
            )
            db.add(version)
            await db.flush()
            pkg.current_version_id = version.id
            await db.commit()
            file_id = file_rec.id
            package_id = pkg.id

        try:
            result = await _cap_get_file_content({"file_id": file_id}, f"user:{owner_id}")

            assert result["success"] is False
            assert result["error"] == "Content package contains no consumable blocks"
            assert result["data"]["source"] == "content_package"
            assert result["data"]["status"] == "parsed"
            assert result["data"]["package_id"] == package_id
            assert "blocks" not in result["data"]
        finally:
            async with AsyncSessionLocal() as cleanup_db:
                await _delete_content_packages(cleanup_db, [package_id])
                await _delete_files(cleanup_db, [file_id])

    @pytest.mark.asyncio
    async def test_get_file_content_returns_degraded_package_body(self):
        from app.database import AsyncSessionLocal
        from app.models.content import ContentPackage, ContentPackageVersion
        from app.models.file import File
        from app.routers.content import _cap_get_file_content

        owner_id = 4
        async with AsyncSessionLocal() as db:
            file_rec = File(
                name=f"degraded-read-{uuid.uuid4().hex}",
                extension="pdf",
                size=0,
                owner_id=owner_id,
                storage_path="missing-degraded-read.pdf",
                mime_type="application/pdf",
                deleted=False,
            )
            db.add(file_rec)
            await db.flush()
            pkg = ContentPackage(
                owner_id=owner_id,
                source_file_id=file_rec.id,
                package_type="document",
                origin_type="uploaded",
                source_extension="pdf",
                status="degraded",
                manifest_json=json.dumps({"title": file_rec.name}, ensure_ascii=False),
            )
            db.add(pkg)
            await db.flush()
            version = ContentPackageVersion(
                package_id=pkg.id,
                version_no=1,
                content_json=json.dumps({
                    "manifest": {"title": file_rec.name},
                    "blocks": [{"id": "b1", "type": "paragraph", "text": "kept degraded正文"}],
                    "resource_diagnostics": [{"status": "failed", "code": "resource_store_failed"}],
                    "parse_status": "degraded",
                }, ensure_ascii=False),
                operation_type="parse",
                created_by=owner_id,
            )
            db.add(version)
            await db.flush()
            pkg.current_version_id = version.id
            await db.commit()
            file_id = file_rec.id
            package_id = pkg.id

        try:
            result = await _cap_get_file_content({"file_id": file_id}, f"user:{owner_id}")

            assert result["success"] is True
            data = result["data"]
            assert data["source"] == "content_package"
            assert data["status"] == "degraded"
            assert data["package_id"] == package_id
            assert data["blocks"][0]["text"] == "kept degraded正文"
        finally:
            async with AsyncSessionLocal() as cleanup_db:
                await _delete_content_packages(cleanup_db, [package_id])
                await _delete_files(cleanup_db, [file_id])

    @pytest.mark.asyncio
    async def test_file_uploaded_handler_propagates_pipeline_failure(self):
        from app.routers import content

        async def failed_pipeline(_payload, _caller, _caller_role):
            return {"status": "failed", "error": "parser returned no blocks"}

        with mock.patch.object(content.pipeline_svc, "handle_file_uploaded", failed_pipeline):
            result = await content._on_file_uploaded(
                {"file_id": 123},
                "user:4",
                "editor",
            )

        assert result["success"] is False
        assert result["error"] == "parser returned no blocks"
        assert result["data"]["status"] == "failed"


# ====================================================================
# 5. Agent policy tests
# ====================================================================


class TestAgentPolicy:
    """Tests for Agent action policy enforcement."""

    @pytest.mark.asyncio
    async def test_system_caller_validate_ir_allowed(self):
        """system:agent-engine can call validate_ir (viewer-level, no owner needed)."""
        from app.services.module_registry import call_capability

        result = await call_capability(
            "content", "validate_ir",
            {"content_ir": _valid_document_ir()},
            caller="system:agent-engine",
            caller_role="viewer",
        )
        if isinstance(result, dict):
            inner = result.get("data", result)
            if isinstance(inner, dict):
                error = inner.get("error", result.get("error", ""))
                if error:
                    assert "permission" not in error.lower()
                    assert "denied" not in error.lower()

    @pytest.mark.asyncio
    async def test_system_caller_write_ir_rejected(self):
        """system:agent-engine cannot call write_ir (needs real user)."""
        from app.services.module_registry import call_capability

        result = await call_capability(
            "content", "write_ir",
            {"content_ir": _valid_document_ir()},
            caller="system:agent-engine",
            caller_role="editor",
        )
        if isinstance(result, dict):
            error = result.get("error", "")
            data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
            err_msg = error or data.get("error", "")
            # Must fail
            if not err_msg:
                # If it didn't fail, at least validate that success is False
                success = result.get("success", data.get("success", True))
                assert success is not True, "system principal must not be able to write"

    @pytest.mark.asyncio
    async def test_system_principal_returns_zero(self):
        """system:* principal returns 0 (no user context)."""
        from app.services.file_reader import is_system_caller, resolve_caller_user_id

        uid = resolve_caller_user_id("system:agent-engine")
        assert uid == 0
        assert is_system_caller("system:agent-engine") is True
        assert is_system_caller("user:4") is False

    @pytest.mark.asyncio
    async def test_system_hard_blocked_actions(self):
        """Verify all expected actions are in SYSTEM_HARD_BLOCKED_ACTIONS."""
        from modules.agent.backend.services.action_policy import (
            SENSITIVE_ACTION_PATTERNS,
            SYSTEM_HARD_BLOCKED_ACTIONS,
        )

        expected = {
            "office-gen__docx",
            "office-gen__xlsx",
            "office-gen__pptx",
            "office-gen__pdf",
            "office-gen__replace_existing",
            "office-gen__generate_to_artifact",
            "office-gen__export_to_artifact",
            "office-gen__convert",
            "desktop-tools__write_file",
            "desktop-tools__replace_file",
            "desktop-tools__create_file",
            "desktop-tools__publish_artifact",
            "desktop-tools__replace_file_from_artifact",
        }
        for action in expected:
            assert action in SYSTEM_HARD_BLOCKED_ACTIONS, f"{action} should be hard blocked"

        # Also verify they are in SENSITIVE_ACTION_PATTERNS
        for action in expected:
            module = action.split("__")[0]
            assert any(
                module in p or action == p
                for p in SENSITIVE_ACTION_PATTERNS
            ), f"{action} should be in sensitive patterns"

    @pytest.mark.asyncio
    async def test_check_action_allowed_hard_blocks_system(self):
        """check_action_allowed(user_id=0) should hard block sensitive actions."""
        from app.database import AsyncSessionLocal

        from modules.agent.backend.services.action_policy import (
            SYSTEM_HARD_BLOCKED_ACTIONS,
            check_action_allowed,
        )

        sample_action = next(iter(SYSTEM_HARD_BLOCKED_ACTIONS))
        async with AsyncSessionLocal() as db:
            result = await check_action_allowed(
                db, sample_action, "test_agent", user_id=0,
            )
        assert result.get("allowed") is False
        assert result.get("action") == "block"

    @pytest.mark.asyncio
    async def test_normal_user_not_blocked_for_same_action(self):
        """Normal user (user_id>0) gets policy-based decision, not hard block."""
        from app.database import AsyncSessionLocal

        from modules.agent.backend.services.action_policy import (
            SYSTEM_HARD_BLOCKED_ACTIONS,
            check_action_allowed,
        )

        sample_action = next(iter(SYSTEM_HARD_BLOCKED_ACTIONS))
        async with AsyncSessionLocal() as db:
            result = await check_action_allowed(
                db, sample_action, "test_agent", user_id=4,
            )
        # Normal user should get a policy decision (could be blocked or confirm)
        # but NOT the hard block message
        if not result.get("allowed"):
            reason = result.get("reason", "")
            assert "hard blocked for system principal" not in reason

    @pytest.mark.asyncio
    async def test_system_caller_can_validate_ir_via_api(self):
        """system:agent-engine can call validate_ir through module_registry."""
        from app.services.module_registry import call_capability

        result = await call_capability(
            "content", "validate_ir",
            {"content_ir": _valid_document_ir()},
            caller="system:agent-engine",
            caller_role="viewer",
        )
        # Must not raise permission error; may succeed or fail on content
        if isinstance(result, dict):
            err = result.get("error", "")
            assert "permission" not in err.lower()


# ====================================================================
# 6. Correction loop constants
# ====================================================================


class TestCorrectionLoopConstants:
    """Test the correction loop limits and prompt template."""

    def test_max_retries_is_3(self):
        from modules.agent.backend.services.content_ir_correction import MAX_RETRIES

        assert MAX_RETRIES == 3

    def test_correction_prompt_contains_errors_placeholder(self):
        from modules.agent.backend.services.content_ir_correction import CORRECTION_PROMPT

        assert "{validation_errors}" in CORRECTION_PROMPT


# ====================================================================
# 7. Capability registration tests
# ====================================================================


class TestCapabilityRegistration:
    """Content IR capabilities must be registered with correct min_role."""

    def test_content_capabilities_listed(self):
        from app.services.module_registry import list_capabilities
        caps = list_capabilities()
        content_caps = {c["action"]: c["min_role"] for c in caps if c["module"] == "content"}

        assert content_caps.get("validate_ir") == "viewer"
        assert content_caps.get("normalize_ir") == "viewer"
        assert content_caps.get("write_ir") == "editor"
        assert content_caps.get("compile") == "viewer"
        assert content_caps.get("store_analysis_resource") == "viewer"

    def test_excel_capabilities_listed(self):
        from app.services.module_registry import list_capabilities
        caps = list_capabilities()
        excel_caps = {c["action"]: c["min_role"] for c in caps if c["module"] == "excel-engine"}

        assert excel_caps.get("compile_xlsx") == "viewer"
        assert excel_caps.get("export_xlsx") == "editor"

    def test_image_vision_capability_listed(self):
        from app.services.module_registry import list_capabilities
        caps = list_capabilities()
        iv_caps = {c["action"]: c["min_role"] for c in caps if c["module"] == "image-vision"}
        assert iv_caps.get("describe") == "viewer"
