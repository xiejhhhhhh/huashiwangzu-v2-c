"""Office JSON patch flow tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

SEED_PASS = "admin123"


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/login", json={"username": "admin", "password": SEED_PASS})
    return resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_office_patch_routes_require_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/office/patch/preview", json={})
        assert resp.status_code == 401

        resp = await client.post("/api/office/patch/apply", json={})
        assert resp.status_code == 401

        resp = await client.post("/api/office/rollback", json={})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_office_package_versions_for_nonexistent() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client)}"}
        resp = await client.get("/api/office/package/99999/versions", headers=headers)
        # May return 404 or empty list
        assert resp.status_code in (200, 404)
