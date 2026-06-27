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
async def test_full_file_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client)}"}
        fr = await client.post("/api/files/folder", json={"name": "e2e-folder"}, headers=headers)
        folder_id = fr.json()["data"]["id"]
        resp = await client.post("/api/files/upload", files={"file": ("e2e.txt", b"e2e content")}, data={"folder_id": folder_id}, headers=headers)
        fid = resp.json()["data"]["id"]
        resp = await client.get(f"/api/files/list?folder_id={folder_id}", headers=headers)
        assert any(item["id"] == fid for item in resp.json()["data"]["items"])
        resp = await client.get("/api/files/search?keyword=e2e", headers=headers)
        assert resp.json()["success"]
        await client.post("/api/files/move", json={"type": "file", "id": fid, "target_folder_id": None}, headers=headers)
        resp = await client.post("/api/files/copy", json={"type": "file", "id": fid, "target_folder_id": folder_id}, headers=headers)
        cid = resp.json()["data"]["id"]
        await client.post("/api/files/delete", json={"type": "file", "id": fid}, headers=headers)
        resp = await client.get("/api/recycle/list", headers=headers)
        rid = next((item["id"] for item in resp.json()["data"] if item["origin_id"] == fid), None)
        assert rid is not None
        await client.post("/api/recycle/restore", json={"item_type": "file", "id": rid}, headers=headers)
        await _del_file(client, headers, fid)
        await _del_file(client, headers, cid)
        await _del_folder(client, headers, folder_id)
