"""Regression tests for cross-module call response truthfulness."""

from types import SimpleNamespace

import pytest
from app.core.exceptions import ValidationError
from app.routers import modules as modules_router
from app.services.module_registry import semantic_failure_reason


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"success": False, "error": "tool failed"}, "tool failed"),
        ({"error": "error-only failure"}, "error-only failure"),
        ({"status": "failed", "error": "status failed"}, "status failed"),
        ({"status": "failed", "reason": "parse failed clearly"}, "parse failed clearly"),
        ({"status": "failed", "error_message": "queue failed clearly"}, "queue failed clearly"),
        ({"status": "failed", "message": "message failed clearly"}, "message failed clearly"),
        ({"status": "error"}, "result.status=error"),
        ({"code": 1, "msg": "legacy failed"}, "legacy failed"),
        ({"success": True, "data": {"success": False, "error": "inner failed"}}, "inner failed"),
        ({"success": True, "data": {"error": "inner error-only"}}, "inner error-only"),
    ],
)
def test_semantic_failure_reason_covers_false_green_shapes(payload, expected) -> None:
    assert semantic_failure_reason(payload) == expected


def test_semantic_failure_reason_allows_non_failure_status() -> None:
    assert semantic_failure_reason({"status": "skipped", "reason": "source_file_deleted"}) is None
    assert semantic_failure_reason({"status": "degraded", "reason": "partial"}) is None


@pytest.mark.asyncio
async def test_module_call_preserves_capability_failure_status(monkeypatch) -> None:
    async def fake_call_capability(*args, **kwargs):
        return {"success": True, "data": {"error": "inner failure"}}

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
    assert exc_info.value.message == "inner failure"
