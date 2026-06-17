"""Office JSON versioning tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

SEED_PASS = "admin123"


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/login", json={"username": "admin", "password": SEED_PASS})
    return resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_office_package_requires_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/office/package", json={"file_id": 999, "format_type": "txt"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_office_versions_requires_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/office/package/1/versions")
        assert resp.status_code == 401
