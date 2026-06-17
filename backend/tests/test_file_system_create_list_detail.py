"""Test file system: create folder, list files, get file detail."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

SEED_PASS = "admin123"


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/login", json={"username": "admin", "password": SEED_PASS})
    data = resp.json()
    assert data["success"] is True
    return data["data"]["access_token"]


async def _cleanup_folder(client: AsyncClient, headers: dict, folder_id: int):
    await client.post("/api/files/delete", json={"type": "folder", "id": folder_id}, headers=headers)
    resp = await client.get("/api/recycle/list", headers=headers)
    for item in resp.json()["data"]:
        if item["origin_id"] == folder_id:
            await client.post("/api/recycle/delete-permanently", json={"item_type": item["item_type"], "id": item["id"]}, headers=headers)


@pytest.mark.asyncio
async def test_create_folder_and_list() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/files/folder", json={"name": "test-folder-001", "parent_id": None}, headers=headers)
        data = resp.json()
        assert data["success"] is True
        folder_id = data["data"]["id"]

        resp = await client.get("/api/files/list?folder_id=0", headers=headers)
        data = resp.json()
        assert data["success"] is True
        folders = [item for item in data["data"]["items"] if item["is_folder"]]
        assert any(f["id"] == folder_id for f in folders)

        await _cleanup_folder(client, headers, folder_id)


@pytest.mark.asyncio
async def test_create_folder_conflict_returns_409() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/files/folder", json={"name": "test-dup-folder", "parent_id": None}, headers=headers)
        data = resp.json()
        assert data["success"] is True
        fid = data["data"]["id"]

        resp2 = await client.post("/api/files/folder", json={"name": "test-dup-folder", "parent_id": None}, headers=headers)
        assert resp2.status_code == 409

        await _cleanup_folder(client, headers, fid)


@pytest.mark.asyncio
async def test_get_file_detail_not_found() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/files/detail/999999", headers=headers)
        assert resp.status_code == 404
