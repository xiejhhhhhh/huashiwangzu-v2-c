"""Test file system: upload, download, preview."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.exceptions import ValidationError
from app.main import app
from app.routers import file_transfer
from httpx import ASGITransport, AsyncClient

SEED_PASS = "admin123"


class _MemoryUpload:
    def __init__(self, filename: str, chunks: list[bytes]) -> None:
        self.filename = filename
        self._chunks = list(chunks)

    async def read(self, _size: int = -1) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/login", json={"username": "admin", "password": SEED_PASS})
    return resp.json()["data"]["access_token"]


async def _cleanup(client: AsyncClient, headers: dict, file_id: int) -> None:
    await client.post("/api/files/delete", json={"type": "file", "id": file_id}, headers=headers)
    resp = await client.get("/api/recycle/list", headers=headers)
    for item in resp.json()["data"]:
        if item["origin_id"] == file_id:
            await client.post("/api/recycle/delete-permanently", json={"item_type": item["item_type"], "id": item["id"]}, headers=headers)


def _patch_upload_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(
        file_transfer,
        "get_settings",
        lambda: SimpleNamespace(UPLOAD_DIR=str(upload_root)),
    )
    return upload_root.parent / ".tmp_uploads"


def _assert_tmp_upload_dir_empty(tmp_upload_dir: Path) -> None:
    assert tmp_upload_dir.exists()
    assert list(tmp_upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_upload_txt_and_download() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        files = {"file": ("test.txt", b"hello world")}
        resp = await client.post("/api/files/upload", files=files, headers=headers)
        data = resp.json()
        assert data["success"] is True
        file_id = data["data"]["id"]
        resp = await client.get(f"/api/files/download/{file_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.content == b"hello world"
        resp = await client.get(f"/api/files/preview/{file_id}", headers=headers)
        data = resp.json()
        assert data["success"] is True
        assert "hello world" in data["data"]["content"]
        await _cleanup(client, headers, file_id)

@pytest.mark.asyncio
async def test_upload_folder_not_found() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.post("/api/files/upload", files={"file": ("test.txt", b"x")}, data={"folder_id": 999999}, headers=headers)
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_empty_file_cleans_temp_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tmp_upload_dir = _patch_upload_dir(monkeypatch, tmp_path)
    user = SimpleNamespace(id=1, role="editor")

    with pytest.raises(ValidationError):
        await file_transfer.upload(
            file=_MemoryUpload("empty.txt", [b""]),
            folder_id=0,
            relative_path="",
            db=object(),
            user=user,
        )

    _assert_tmp_upload_dir_empty(tmp_upload_dir)


@pytest.mark.asyncio
async def test_upload_too_large_cleans_temp_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tmp_upload_dir = _patch_upload_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(file_transfer, "MAX_UPLOAD_BYTES", 3)
    user = SimpleNamespace(id=1, role="editor")

    with pytest.raises(ValidationError):
        await file_transfer.upload(
            file=_MemoryUpload("too-large.txt", [b"abcd"]),
            folder_id=0,
            relative_path="",
            db=object(),
            user=user,
        )

    _assert_tmp_upload_dir_empty(tmp_upload_dir)


@pytest.mark.asyncio
async def test_upload_service_exception_cleans_temp_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tmp_upload_dir = _patch_upload_dir(monkeypatch, tmp_path)
    user = SimpleNamespace(id=1, role="editor")

    async def fail_upload_from_path(*args, **kwargs):
        temp_path = args[1]
        assert temp_path.exists()
        raise RuntimeError("upload failed")

    monkeypatch.setattr(
        file_transfer.file_upload_service,
        "upload_file_from_path",
        fail_upload_from_path,
    )

    with pytest.raises(RuntimeError, match="upload failed"):
        await file_transfer.upload(
            file=_MemoryUpload("service-error.txt", [b"content"]),
            folder_id=0,
            relative_path="",
            db=object(),
            user=user,
        )

    _assert_tmp_upload_dir_empty(tmp_upload_dir)


@pytest.mark.asyncio
async def test_download_not_found() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/files/download/999999", headers=headers)
        assert resp.status_code == 404
