from app.schemas.desktop_state import DesktopAuditLogRequest, DesktopStateSaveRequest


def test_desktop_state_save_request_schema_accepts_state_json():
    body = DesktopStateSaveRequest(state_json={"窗口": []})
    assert body.state_json == {"窗口": []}


def test_desktop_audit_log_request_schema_has_action_fields():
    body = DesktopAuditLogRequest(action="open_app", params={"app": "dashboard"}, target_app="dashboard")
    assert body.action == "open_app"
    assert body.params == {"app": "dashboard"}
    assert body.target_app == "dashboard"
