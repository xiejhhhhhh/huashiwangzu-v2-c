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
async def test_share_and_check_access():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ah = {"Authorization": f"Bearer {await _login(client, 'admin')}"}
        vh = {"Authorization": f"Bearer {await _login(client, 'viewer')}"}
        resp = await client.post("/api/files/upload", files={"file": ("share-me.txt", b"shared content")}, headers=ah)
        fid = resp.json()["data"]["id"]
        resp = await client.get(f"/api/files/share/check/{fid}", headers=vh)
        assert resp.json()["data"]["accessible"] is False
        resp = await client.post("/api/files/share", json={"file_id": fid, "target_user_id": 2, "permission": "read"}, headers=ah)
        assert resp.json()["success"]
        sid = resp.json()["data"]["id"]
        resp = await client.get(f"/api/files/share/check/{fid}", headers=vh)
        assert resp.json()["data"]["accessible"] is True
        assert resp.json()["data"]["permission"] == "read"
        resp = await client.get("/api/files/share/received", headers=vh)
        assert resp.json()["success"]
        resp = await client.get("/api/files/share/sent", headers=ah)
        assert resp.json()["success"]
        resp = await client.delete(f"/api/files/share/{sid}", headers=ah)
        assert resp.json()["success"]
        resp = await client.get(f"/api/files/share/check/{fid}", headers=vh)
        assert resp.json()["data"]["accessible"] is False
        await _del_file(client, ah, fid)

@pytest.mark.asyncio
async def test_non_owner_cannot_share():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ah = {"Authorization": f"Bearer {await _login(client, 'admin')}"}
        vh = {"Authorization": f"Bearer {await _login(client, 'viewer')}"}
        resp = await client.post("/api/files/upload", files={"file": ("mine.txt", b"mine")}, headers=ah)
        fid = resp.json()["data"]["id"]
        resp = await client.post("/api/files/share", json={"file_id": fid, "target_user_id": 1, "permission": "read"}, headers=vh)
        assert resp.status_code == 403
        await _del_file(client, ah, fid)
