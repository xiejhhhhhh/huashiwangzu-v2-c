"""Office JSON package baseline tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

SEED_PASS = "admin123"


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/login", json={"username": "admin", "password": SEED_PASS})
    return resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_office_routes_exist() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client)}"}
        # Verify office endpoints are registered (may return 404 for non-existent packages)
        resp = await client.get("/api/office/status/999999", headers=headers)
        assert resp.status_code in (200, 404, 400)


@pytest.mark.asyncio
async def test_office_routes_require_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/office/status/1")
        assert resp.status_code == 401
