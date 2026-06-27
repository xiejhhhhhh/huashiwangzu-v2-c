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
async def test_delete_and_restore_file():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client)}"}
        fid = await _upload(client, headers, "to-delete.txt", b"delete me")
        await client.post("/api/files/delete", json={"type": "file", "id": fid}, headers=headers)
        resp = await client.get("/api/recycle/list", headers=headers)
        rid = next((item["id"] for item in resp.json()["data"] if item["origin_id"] == fid), None)
        assert rid is not None
        resp = await client.post("/api/recycle/restore", json={"item_type": "file", "id": rid}, headers=headers)
        assert resp.json()["success"]
        await _del_file(client, headers, fid)

@pytest.mark.asyncio
async def test_permanent_delete():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client)}"}
        fid = await _upload(client, headers, "perm-delete.txt", b"permanent")
        await client.post("/api/files/delete", json={"type": "file", "id": fid}, headers=headers)
        resp = await client.get("/api/recycle/list", headers=headers)
        rid = next((item["id"] for item in resp.json()["data"] if item["origin_id"] == fid), None)
        assert rid is not None
        resp = await client.post("/api/recycle/delete-permanently", json={"item_type": "file", "id": rid}, headers=headers)
        assert resp.json()["success"]

@pytest.mark.asyncio
async def test_empty_trash():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client)}"}
        resp = await client.post("/api/recycle/empty", headers=headers)
        assert resp.json()["success"]
