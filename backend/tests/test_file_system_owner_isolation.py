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
async def test_user_cannot_list_other_files():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ah = {"Authorization": f"Bearer {await _login(client, 'admin')}"}
        vh = {"Authorization": f"Bearer {await _login(client, 'viewer')}"}
        resp = await client.post("/api/files/upload", files={"file": ("admin-file.txt", b"secret")}, headers=ah)
        fid = resp.json()["data"]["id"]
        resp = await client.get("/api/files/list?folder_id=0", headers=vh)
        for item in resp.json()["data"]["items"]:
            assert item["id"] != fid
        resp = await client.get(f"/api/files/detail/{fid}", headers=vh)
        assert resp.status_code == 404
        resp = await client.get(f"/api/files/download/{fid}", headers=vh)
        assert resp.status_code in (403, 404)
        await _del_file(client, ah, fid)

@pytest.mark.asyncio
async def test_user_cannot_search_other_files():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ah = {"Authorization": f"Bearer {await _login(client, 'admin')}"}
        vh = {"Authorization": f"Bearer {await _login(client, 'viewer')}"}
        resp = await client.post("/api/files/upload", files={"file": ("secret-search.txt", b"classified")}, headers=ah)
        fid = resp.json()["data"]["id"]
        resp = await client.get("/api/files/search?keyword=secret", headers=vh)
        for item in resp.json()["data"]["items"]:
            assert item["id"] != fid
        await _del_file(client, ah, fid)
