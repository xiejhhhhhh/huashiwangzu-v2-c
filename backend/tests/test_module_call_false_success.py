"""Regression tests for cross-module call response truthfulness."""

from types import SimpleNamespace

import pytest
from app.core.exceptions import ValidationError
from app.routers import modules as modules_router


@pytest.mark.asyncio
async def test_module_call_preserves_capability_failure_status(monkeypatch) -> None:
    async def fake_call_capability(*args, **kwargs):
        return {"success": False, "error": "tool failed", "data": {"detail": "blocked"}}

    monkeypatch.setattr(modules_router, "call_capability", fake_call_capability)

    with pytest.raises(ValidationError) as exc_info:
        await modules_router.module_call(
            modules_router.ModuleCallRequest(
                target_module="demo",
                action="run",
                parameters={},
            ),
            user=SimpleNamespace(id=1, role="viewer"),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.message == "tool failed"
