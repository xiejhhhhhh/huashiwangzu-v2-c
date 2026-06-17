"""Test file system: upload, download, preview."""
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

SEED_PASS = "admin123"

async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/login", json={"username": "admin", "password": SEED_PASS})
    return resp.json()["data"]["access_token"]

async def _cleanup(client: AsyncClient, headers: dict, file_id: int):
    await client.post("/api/files/delete", json={"type": "file", "id": file_id}, headers=headers)
    resp = await client.get("/api/recycle/list", headers=headers)
    for item in resp.json()["data"]:
        if item["origin_id"] == file_id:
            await client.post("/api/recycle/delete-permanently", json={"item_type": item["item_type"], "id": item["id"]}, headers=headers)

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
async def test_download_not_found() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/files/download/999999", headers=headers)
        assert resp.status_code == 404
