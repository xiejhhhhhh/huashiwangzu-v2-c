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
async def test_same_content_dedup():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client, 'admin')}"}
        import os as _os
        content = b"unique dedup " + _os.urandom(8)
        resp1 = await client.post("/api/files/upload", files={"file": ("dedup1.txt", content)}, headers=headers)
        assert resp1.json()["success"]
        id1 = resp1.json()["data"]["id"]
        resp2 = await client.post("/api/files/upload", files={"file": ("dedup2.txt", content)}, headers=headers)
        assert resp2.json()["success"]
        id2 = resp2.json()["data"]["id"]
        assert resp2.json()["data"]["deduplicated"] is True
        await _del_file(client, headers, id1)
        await _del_file(client, headers, id2)

@pytest.mark.asyncio
async def test_diff_content_not_dedup():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client, 'admin')}"}
        r1 = await client.post("/api/files/upload", files={"file": ("a.txt", b"aaa")}, headers=headers)
        r2 = await client.post("/api/files/upload", files={"file": ("b.txt", b"bbb")}, headers=headers)
        assert r1.json()["success"] and r2.json()["success"]
        assert r2.json()["data"].get("deduplicated") is not True
        await _del_file(client, headers, r1.json()["data"]["id"])
        await _del_file(client, headers, r2.json()["data"]["id"])
