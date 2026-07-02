"""Regression tests for cross-module call response truthfulness."""

from types import SimpleNamespace

import pytest
from app.routers import modules as modules_router


@pytest.mark.asyncio
async def test_module_call_preserves_capability_failure_status(monkeypatch) -> None:
    async def fake_call_capability(*args, **kwargs):
        return {"success": False, "error": "tool failed", "data": {"detail": "blocked"}}

    monkeypatch.setattr(modules_router, "call_capability", fake_call_capability)

    response = await modules_router.module_call(
        modules_router.ModuleCallRequest(
            target_module="demo",
            action="run",
            parameters={},
        ),
        user=SimpleNamespace(id=1, role="viewer"),
    )

    assert response.success is False
    assert response.error == "tool failed"
    assert response.data["success"] is False
