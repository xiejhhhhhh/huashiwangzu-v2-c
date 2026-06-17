"""Office file delete cleanup tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

SEED_PASS = "admin123"


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/login", json={"username": "admin", "password": SEED_PASS})
    return resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_office_status_not_found_for_deleted() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client)}"}
        resp = await client.get("/api/office/status/999999", headers=headers)
        # Should return either success with no package or 404
        assert resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_office_routes_protected() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path, method in [("/api/office/status/1", "GET"), ("/api/office/package", "POST"), ("/api/office/package/1", "GET")]:
            if method == "GET":
                resp = await client.get(path)
            else:
                resp = await client.post(path, json={})
            assert resp.status_code == 401
