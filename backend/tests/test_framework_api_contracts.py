from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers.roles import export_matrix


@pytest.mark.asyncio
async def test_protected_desktop_route_returns_401_json_contract() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/desktop/apps")

    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["data"] is None
    assert data["error"] == "Authentication required"


@pytest.mark.asyncio
async def test_desktop_state_route_exists_and_requires_authentication() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/desktop/state",
            json={"state_json": {"version": 1, "windows": [], "appState": {}}},
        )

    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["data"] is None


@pytest.mark.asyncio
async def test_role_matrix_export_keeps_csv_response() -> None:
    matrix = [{
        "role_key": "admin",
        "display_name": "Admin",
        "permissions": {
            "user_management": True,
            "system_config": True,
            "role_matrix": True,
        },
    }]
    with patch("app.routers.roles.get_role_matrix", AsyncMock(return_value=matrix)):
        response = await export_matrix(db=object(), current_user=SimpleNamespace(id=1))

    assert response.media_type == "text/csv; charset=utf-8"
    assert b"role_key,display_name" in response.body
