from app.main import app


def test_new_routes_exist():
    paths = app.openapi()["paths"]
    assert "/api/desktop/apps/{app_key}" in paths
    assert "/api/app-manager/apps/scan-register" in paths
    assert "/api/roles/matrix/export" in paths
    assert "/api/agent/prompts/{prompt_id}/copy" in paths
    assert "/api/agent/prompts/{prompt_id}/set-default" in paths
    assert "/api/agent/prompts/{prompt_id}/toggle-enabled" in paths
    assert "/api/knowledge/labels/index/{catalog_id}" in paths


def test_prompt_service_to_dict_exports_expected_keys():
    from app.services.agent.prompt_service import prompt_service

    class Dummy:
        id = 1
        name = "demo"
        content = "hello"
        category_id = None
        variables = None
        description = None
        is_default = False
        is_enabled = True
        created_at = None
        updated_at = None

    data = prompt_service.to_dict(Dummy())
    assert data["name"] == "demo"
    assert data["isEnabled"] is True
