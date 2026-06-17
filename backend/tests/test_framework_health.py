from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


class FakeConnection:
    async def execute(self, statement: object) -> None:
        return None


class FakeConnectionContext:
    async def __aenter__(self) -> FakeConnection:
        return FakeConnection()

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeEngine:
    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext()


class BrokenEngine:
    def connect(self) -> FakeConnectionContext:
        raise RuntimeError("db down")


@pytest.mark.asyncio
async def test_health_endpoint_reports_database_status_ok() -> None:
    transport = ASGITransport(app=app)

    with patch("app.database.engine", FakeEngine()):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "ok"
    assert data["data"]["database"] == "ok"


@pytest.mark.asyncio
async def test_health_endpoint_reports_database_status_unreachable() -> None:
    transport = ASGITransport(app=app)

    with patch("app.database.engine", BrokenEngine()):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["database"] == "unreachable"
