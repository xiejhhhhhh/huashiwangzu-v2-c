import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_api_404_returns_unified_json_contract() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/nonexistent-route-xyz")

    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["data"] is None
    assert data["error"]
    assert "detail" not in data


@pytest.mark.asyncio
async def test_validation_error_returns_unified_json_contract() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/login", json={"bad_field": 123})

    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["data"] is None
    assert data["error"] == "Validation failed"
    assert isinstance(data["errors"], dict)
