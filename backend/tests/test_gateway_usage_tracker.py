from __future__ import annotations

from pathlib import Path
from types import TracebackType

import pytest
from app.gateway import config as gateway_config
from app.gateway import usage_tracker
from app.models.base import Base
from app.models.gateway_usage import GatewayUsageDaily

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_gateway_usage_model_uses_framework_table() -> None:
    table = GatewayUsageDaily.__table__

    assert table.name == "framework_gateway_usage_daily"
    assert table.name in Base.metadata.tables
    assert {
        "usage_date",
        "model_key",
        "provider",
        "module",
        "call_count",
        "prompt_tokens",
        "completion_tokens",
        "cost",
    }.issubset(table.columns.keys())


def test_usage_tracker_does_not_reference_agent_usage_table() -> None:
    source = (PROJECT_ROOT / "backend/app/gateway/usage_tracker.py").read_text(
        encoding="utf-8"
    )

    assert "agent_usage_daily" not in source
    assert "framework_gateway_usage_daily" in source


@pytest.mark.asyncio
async def test_log_usage_writes_framework_gateway_usage_table(monkeypatch) -> None:
    executed: list[tuple[str, dict[str, object]]] = []

    class FakeSession:
        async def __aenter__(self) -> "FakeSession":
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            return None

        async def execute(
            self,
            statement: object,
            parameters: dict[str, object],
        ) -> None:
            executed.append((str(statement), dict(parameters)))

        async def commit(self) -> None:
            return None

    monkeypatch.setattr(
        gateway_config,
        "MODEL_PROFILES",
        {"priced-model": {"price_input": 2.0, "price_output": 4.0}},
    )

    import app.database as database

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: FakeSession())

    await usage_tracker.log_usage(
        model_key="priced-model",
        provider_name="deepseek",
        caller_module="gateway.chat",
        prompt_tokens=100,
        completion_tokens=50,
    )

    assert len(executed) == 1
    sql, parameters = executed[0]
    assert "INSERT INTO framework_gateway_usage_daily" in sql
    assert "agent_usage_daily" not in sql
    assert parameters["model"] == "priced-model"
    assert parameters["provider"] == "deepseek"
    assert parameters["module"] == "gateway.chat"
    assert parameters["prompt_tokens"] == 100
    assert parameters["completion_tokens"] == 50
    assert parameters["cost"] == pytest.approx(0.0004)
