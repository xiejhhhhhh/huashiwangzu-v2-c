from app.main import app


def test_knowledge_governance_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    assert "/api/knowledge/evidences" in paths
    assert "/api/knowledge/evidences/{evidence_id}/bind-conclusions" in paths
    assert "/api/knowledge/candidates/pending-count" in paths
    assert "/api/knowledge/graph/overview" in paths
    assert "/api/knowledge/graph/search" in paths
    assert "/api/knowledge/graph/by-business/{node_type}/{business_id}" in paths
    assert "/api/knowledge/candidates/{candidate_id}/confirm" in paths
    assert "/api/knowledge/entities" in paths
    assert "/api/knowledge/entities/{entity_id}" in paths
    assert "/api/knowledge/entities/aliases/{alias_id}/disable" in paths
    assert "/api/knowledge/entities/disambiguation/scan" in paths
    assert "/api/knowledge/entities/merge" in paths
    assert "/api/knowledge/aggregation/entities/{entity_id}" in paths
    assert "/api/knowledge/aggregation/entities/{entity_id}/refresh-suggestions" in paths
    assert "/api/knowledge/visual/page-image/{catalog_id}/{page_num}" in paths
    assert "/api/knowledge/visual/thumbnail/{catalog_id}/{page_num}" in paths
    assert "/api/knowledge/evaluation/overview" in paths
    assert "/api/knowledge/evaluation/history" in paths
    assert "/api/knowledge/evaluation/records/{record_id}" in paths
    assert "/api/knowledge/evaluation/run" in paths
    assert "/api/image-vision/trigger" in paths
    assert "/api/image-vision/dry-run" in paths
    assert "/api/image-vision/providers" in paths
    assert "/api/image-vision/status/{catalog_id}" in paths
    assert "/api/image-vision/stats" in paths
    assert "/api/menu" in paths
    assert "/api/health/deep" in paths
    assert "/api/knowledge/labels/search" in paths
    assert "/api/knowledge/labels/files/{catalog_id}" in paths
    assert "/api/knowledge/analysis-results/{catalog_id}" in paths


def test_openapi_operation_ids_are_unique() -> None:
    operation_ids: list[str] = []
    for methods in app.openapi()["paths"].values():
        for operation in methods.values():
            operation_ids.append(operation["operationId"])
    assert len(operation_ids) == len(set(operation_ids))
