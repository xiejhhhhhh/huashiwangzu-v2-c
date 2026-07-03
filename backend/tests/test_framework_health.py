from unittest.mock import patch

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


class FakeConnection:
    async def execute(self, statement: object) -> object:
        sql = str(statement)
        if "GROUP BY status" in sql:
            return FakeRows([])
        if "SELECT count(*)" in sql:
            return FakeScalar(0)
        return FakeScalar(1)


class FakeRows:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class FakeScalar:
    def __init__(self, value: int) -> None:
        self._value = value

    def scalar(self) -> int:
        return self._value


class FakeConnectionContext:
    def __init__(self, connection: FakeConnection | None = None) -> None:
        self.connection = connection or FakeConnection()

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeEngine:
    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext()


class SemanticFailureConnection(FakeConnection):
    async def execute(self, statement: object) -> object:
        sql = str(statement)
        if "GROUP BY status" in sql:
            return FakeRows([])
        if "completed_at >= NOW() - INTERVAL '24 hours'" in sql:
            return FakeScalar(2)
        if "status = 'completed'" in sql and "SELECT count(*)" in sql:
            return FakeScalar(3)
        if "SELECT count(*)" in sql:
            return FakeScalar(0)
        return FakeScalar(1)


class SemanticFailureEngine:
    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext(SemanticFailureConnection())


class BrokenEngine:
    def connect(self) -> FakeConnectionContext:
        raise RuntimeError("db down")


class HistoricalDebtConnection(FakeConnection):
    async def execute(self, statement: object) -> object:
        sql = str(statement)
        if "GROUP BY status" in sql:
            return FakeRows([("failed", 905), ("pending", 1)])
        if "SELECT count(*)" in sql:
            return FakeScalar(0)
        return FakeScalar(1)


class HistoricalDebtEngine:
    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext(HistoricalDebtConnection())


@pytest.mark.asyncio
async def test_health_endpoint_reports_database_status_ok() -> None:
    transport = ASGITransport(app=app)

    with patch("app.database.engine", FakeEngine()), patch(
        "app.services.task_worker.worker_health",
        return_value={"running": True, "registered_handlers": [], "last_active": None},
    ), patch("app.services.event_bus.get_event_log", return_value=[]), patch(
        "app.routers.registry.get_module_load_errors", return_value={}
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "ok"
    assert data["data"]["database"] == "ok"
    assert data["data"]["worker"]["running"] is True


@pytest.mark.asyncio
async def test_health_endpoint_reports_database_status_unreachable() -> None:
    transport = ASGITransport(app=app)

    with patch("app.database.engine", BrokenEngine()), patch(
        "app.services.task_worker.worker_health",
        return_value={"running": True, "registered_handlers": [], "last_active": None},
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "error"
    assert data["data"]["database"] == "unreachable"


@pytest.mark.asyncio
async def test_health_endpoint_reports_worker_stopped_as_degraded() -> None:
    transport = ASGITransport(app=app)

    with patch("app.database.engine", FakeEngine()), patch(
        "app.services.task_worker.worker_health",
        return_value={"running": False, "registered_handlers": [], "last_active": None},
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_endpoint_reports_event_bus_error_as_degraded() -> None:
    transport = ASGITransport(app=app)

    with patch("app.database.engine", FakeEngine()), patch(
        "app.services.task_worker.worker_health",
        return_value={"running": True, "registered_handlers": [], "last_active": None},
    ), patch("app.services.event_bus.get_event_log", side_effect=RuntimeError("event down")):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["status"] == "degraded"
    assert data["data"]["event_bus"] == "error"


@pytest.mark.asyncio
async def test_health_endpoint_reports_module_errors_as_degraded() -> None:
    transport = ASGITransport(app=app)

    with patch("app.database.engine", FakeEngine()), patch(
        "app.services.task_worker.worker_health",
        return_value={"running": True, "registered_handlers": [], "last_active": None},
    ), patch("app.routers.registry.get_module_load_errors", return_value={"bad": "boom"}):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["status"] == "degraded"
    assert data["data"]["module_errors"] == {"bad": "boom"}


@pytest.mark.asyncio
async def test_health_endpoint_reports_task_semantic_failures_as_degraded() -> None:
    transport = ASGITransport(app=app)

    with patch("app.database.engine", SemanticFailureEngine()), patch(
        "app.services.task_worker.worker_health",
        return_value={"running": True, "registered_handlers": [], "last_active": None},
    ), patch("app.services.event_bus.get_event_log", return_value=[]), patch(
        "app.routers.registry.get_module_load_errors", return_value={}
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "degraded"
    assert data["task_queue"]["semantic_failed_completed_24h"] == 2
    assert data["task_queue"]["semantic_failed_completed_total"] == 3


@pytest.mark.asyncio
async def test_health_endpoint_reports_historical_failed_debt_without_degrading_live_health() -> None:
    transport = ASGITransport(app=app)

    with patch("app.database.engine", HistoricalDebtEngine()), patch(
        "app.services.task_worker.worker_health",
        return_value={"running": True, "registered_handlers": [], "last_active": None},
    ), patch("app.services.event_bus.get_event_log", return_value=[]), patch(
        "app.routers.registry.get_module_load_errors", return_value={}
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ok"
    assert data["task_queue"]["failed"] == 905
    assert data["task_queue"]["historical_failed_debt"] == 905
    assert data["task_queue"]["pending"] == 1
    assert data["task_queue"]["debt_status"] == "debt"
