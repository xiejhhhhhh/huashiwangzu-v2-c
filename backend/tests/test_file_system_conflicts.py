import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

SEED_PASS = "admin123"

async def _login(client, username="admin"):
    resp = await client.post("/api/login", json={"username": username, "password": SEED_PASS})
    return resp.json()["data"]["access_token"]

async def _upload(client, headers, name, content=b"test"):
    resp = await client.post("/api/files/upload", files={"file": (name, content)}, headers=headers)
    return resp.json()["data"]["id"]

async def _del_file(client, headers, fid):
    await client.post("/api/files/delete", json={"type": "file", "id": fid}, headers=headers)
    resp = await client.get("/api/recycle/list", headers=headers)
    for item in resp.json()["data"]:
        if item["origin_id"] == fid:
            await client.post("/api/recycle/delete-permanently", json={"item_type": item["item_type"], "id": item["id"]}, headers=headers)

async def _del_folder(client, headers, fid):
    await client.post("/api/files/delete", json={"type": "folder", "id": fid}, headers=headers)
    resp = await client.get("/api/recycle/list", headers=headers)
    for item in resp.json()["data"]:
        if item["origin_id"] == fid:
            await client.post("/api/recycle/delete-permanently", json={"item_type": item["item_type"], "id": item["id"]}, headers=headers)

@pytest.mark.asyncio
async def test_duplicate_upload_returns_409():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client)}"}
        resp = await client.post("/api/files/upload", files={"file": ("dup.txt", b"content")}, headers=headers)
        assert resp.json()["success"]
        fid = resp.json()["data"]["id"]
        resp2 = await client.post("/api/files/upload", files={"file": ("dup.txt", b"content")}, headers=headers)
        assert resp2.status_code == 409
        await _del_file(client, headers, fid)

@pytest.mark.asyncio
async def test_move_folder_to_itself_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client)}"}
        resp = await client.post("/api/files/folder", json={"name": "self-move"}, headers=headers)
        fid = resp.json()["data"]["id"]
        resp2 = await client.post("/api/files/move", json={"type": "folder", "id": fid, "target_folder_id": fid}, headers=headers)
        assert resp2.status_code == 400
        await _del_folder(client, headers, fid)
