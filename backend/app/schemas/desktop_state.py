from pydantic import BaseModel
from typing import Any


class DesktopStateResponse(BaseModel):
    user_id: int
    state_json: dict[str, Any] = {}
    version: int = 1


class DesktopStateSaveRequest(BaseModel):
    state_json: dict[str, Any]


class DesktopAuditLogRequest(BaseModel):
    action: str = ""
    params: dict[str, Any] = {}
    target_app: str = ""
