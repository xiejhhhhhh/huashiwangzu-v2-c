"""Tests for enterprise source-folder import planning helpers."""
import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret-for-enterprise-import")

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest

import modules.knowledge.backend.services.enterprise_import_service as enterprise_import
from modules.knowledge.backend.services.enterprise_import_service import (
    _normalize_extensions,
    _relative_import_path,
    import_enterprise_source_batch,
)


class _ScalarResult:
    def __init__(self, values: list[str] | None = None, one: object | None = None):
        self._values = values or []
        self._one = one

    def scalars(self):
        return self

    def all(self):
        return self._values

    def scalar_one_or_none(self):
        return self._one


class _FakeDb:
    def __init__(self, existing_md5: list[str] | None = None):
        self._existing_md5 = existing_md5 or []
        self._execute_count = 0

    async def execute(self, _stmt):
        self._execute_count += 1
        if self._execute_count == 1:
            return _ScalarResult(self._existing_md5)
        return _ScalarResult()


def test_normalize_extensions_filters_unsupported_and_video() -> None:
    assert _normalize_extensions([".PDF", "mp4", "exe", "tif", "jpg"]) == {"pdf", "tiff", "jpg"}


def test_relative_import_path_preserves_source_parent() -> None:
    assert _relative_import_path("企业微盘导入", Path("品牌/资料/a.pdf")) == "企业微盘导入/品牌/资料"
    assert _relative_import_path("企业微盘导入", Path("a.pdf")) == "企业微盘导入"


@pytest.mark.asyncio
async def test_import_enterprise_source_batch_dry_run_keeps_source_file(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    nested = source_root / "品牌资料"
    nested.mkdir(parents=True)
    source_file = nested / "产品说明.pdf"
    source_file.write_bytes(b"pdf bytes")

    result = await import_enterprise_source_batch(
        _FakeDb(),
        owner_id=4,
        source_root=str(source_root),
        target_root_name="企业微盘导入",
        limit=10,
        dry_run=True,
        extensions=["pdf"],
    )

    assert result["dry_run"] is True
    assert result["selected"] == 1
    assert result["imported"] == 0
    assert result["items"][0]["path"] == "品牌资料/产品说明.pdf"
    assert result["items"][0]["target_relative_path"] == "企业微盘导入/品牌资料"
    assert result["items"][0]["content_action"] == "store_new_content"
    assert source_file.exists()


@pytest.mark.asyncio
async def test_import_enterprise_source_batch_dry_run_keeps_duplicate_logical_file(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    nested = source_root / "品牌A"
    nested.mkdir(parents=True)
    source_file = nested / "重复资料.pdf"
    source_file.write_bytes(b"same bytes")
    duplicate_md5 = enterprise_import._file_md5(source_file)

    result = await import_enterprise_source_batch(
        _FakeDb(existing_md5=[duplicate_md5]),
        owner_id=4,
        source_root=str(source_root),
        target_root_name="企业微盘导入",
        limit=10,
        dry_run=True,
        extensions=["pdf"],
        skip_existing_md5=True,
    )

    assert result["selected"] == 1
    assert result["skipped"] == 0
    assert result["items"][0]["path"] == "品牌A/重复资料.pdf"
    assert result["items"][0]["content_action"] == "reuse_existing_content"


@pytest.mark.asyncio
async def test_import_enterprise_source_batch_reuses_duplicate_content_without_new_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    nested = source_root / "品牌B"
    nested.mkdir(parents=True)
    source_file = nested / "同内容不同目录.pdf"
    source_file.write_bytes(b"same bytes")
    duplicate_md5 = enterprise_import._file_md5(source_file)
    calls: dict[str, object] = {}

    async def fake_upload_file_from_path(
        _db,
        file_path: Path,
        filename: str,
        owner_id: int,
        folder_id=None,
        relative_path=None,
        md5_hex=None,
        mime_type=None,
    ) -> dict:
        calls["upload"] = {
            "file_path_exists": file_path.exists(),
            "filename": filename,
            "owner_id": owner_id,
            "folder_id": folder_id,
            "relative_path": relative_path,
            "md5_hex": md5_hex,
            "mime_type": mime_type,
        }
        return {
            "id": 88,
            "name": "同内容不同目录",
            "extension": "pdf",
            "size": file_path.stat().st_size,
            "mime_type": mime_type,
            "deduplicated": True,
        }

    async def fake_register_document(_db, file_id: int, owner_id: int) -> dict:
        calls["register"] = {"file_id": file_id, "owner_id": owner_id}
        return {
            "document_id": 12,
            "task_id": None,
            "enqueued": False,
            "reason": "content already indexed",
            "duplicate_reused": True,
        }

    monkeypatch.setattr(enterprise_import, "upload_file_from_path", fake_upload_file_from_path)
    monkeypatch.setattr(enterprise_import, "register_document", fake_register_document)

    result = await import_enterprise_source_batch(
        _FakeDb(existing_md5=[duplicate_md5]),
        owner_id=4,
        source_root=str(source_root),
        target_root_name="企业微盘导入",
        limit=10,
        dry_run=False,
        extensions=["pdf"],
        skip_existing_md5=True,
    )

    assert result["selected"] == 1
    assert result["imported"] == 1
    assert result["skipped"] == 0
    assert calls["upload"]["relative_path"] == "企业微盘导入/品牌B"
    assert calls["upload"]["md5_hex"] == duplicate_md5
    assert calls["register"] == {"file_id": 88, "owner_id": 4}
    assert result["items"][0]["deduplicated"] is True
    assert result["items"][0]["duplicate_reused"] is True
    assert result["items"][0]["enqueued"] is False
    assert result["items"][0]["reason"] == "content already indexed"
