from pydantic import BaseModel


class DesktopStateResponse(BaseModel):
    user_id: int
    state_json: dict = {}
    version: int = 1


class DesktopStateSaveRequest(BaseModel):
    state_json: dict
    # WP6 CAS：可选。传入时必须匹配当前 version，否则 409。
    expected_version: int | None = None


class DesktopAuditLogRequest(BaseModel):
    action: str = ""
    params: dict = {}
    target_app: str = ""
