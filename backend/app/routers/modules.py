from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.schemas.common import ApiResponse
from app.middleware.auth import require_permission
from app.models.user import User
from app.services.module_registry import (
    call_capability, list_capabilities, SIDE_EFFECT_LEVELS,
)

router = APIRouter(prefix="/api/modules", tags=["modules"])


class ModuleCallRequest(BaseModel):
    target_module: str
    action: str
    parameters: dict = {}


class ModuleCallWithTraceRequest(BaseModel):
    target_module: str
    action: str
    parameters: dict = {}
    trace_id: str | None = None


@router.post("/call")
async def module_call(payload: ModuleCallRequest, user: User = Depends(require_permission("viewer"))):
    result = await call_capability(
        payload.target_module,
        payload.action,
        payload.parameters,
        caller=f"user:{user.id}",
        caller_role=user.role,
    )
    return ApiResponse(data=result)


@router.post("/call-with-trace")
async def module_call_with_trace(payload: ModuleCallWithTraceRequest, user: User = Depends(require_permission("viewer"))):
    """Cross-module call with explicit trace_id propagation.

    The trace_id flows into _call_with_retry → RetryBudget and downstream
    into task_worker / events for end-to-end observability.
    """
    result = await call_capability(
        payload.target_module,
        payload.action,
        payload.parameters,
        caller=f"user:{user.id}",
        caller_role=user.role,
        trace_id=payload.trace_id,
    )
    return ApiResponse(data=result)


@router.get("/capabilities")
async def capabilities(
    user: User = Depends(require_permission("viewer")),
    side_effect: str | None = Query(None, description="Filter by side_effect_level"),
):
    caps = list_capabilities(role=user.role)
    if side_effect:
        if side_effect not in SIDE_EFFECT_LEVELS:
            return ApiResponse(
                success=False,
                error=f"Invalid side_effect level. Must be one of: {SIDE_EFFECT_LEVELS}",
            )
        caps = [c for c in caps if c.get("side_effect_level") == side_effect]
    return ApiResponse(data=caps)
