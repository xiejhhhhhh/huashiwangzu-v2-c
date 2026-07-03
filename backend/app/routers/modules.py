from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import call_capability, list_capabilities

router = APIRouter(prefix="/api/modules", tags=["modules"])


class ModuleCallRequest(BaseModel):
    target_module: str
    action: str
    parameters: dict = {}


@router.post("/call")
async def module_call(payload: ModuleCallRequest, user: User = Depends(require_permission("viewer"))):
    result = await call_capability(
        payload.target_module,
        payload.action,
        payload.parameters,
        caller=f"user:{user.id}",
        caller_role=user.role,
    )
    if isinstance(result, dict) and result.get("success") is False:
        raise ValidationError(
            str(result.get("error") or f"{payload.target_module}:{payload.action} failed")
        )
    return ApiResponse(data=result)


@router.get("/capabilities")
async def capabilities(user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=list_capabilities(role=user.role, caller=f"user:{user.id}"))
