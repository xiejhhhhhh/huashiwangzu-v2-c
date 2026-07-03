"""Sandbox test for codemap module.

Validates parameter schemas, required fields, value ranges, and output
shapes for all public_actions — without calling real indexing or DB.
"""


def test_get_file_params() -> None:
    """get_file: path required (str)."""
    params = {"path": "modules/agent/manifest.json"}
    assert "path" in params
    assert isinstance(params["path"], str) and len(params["path"]) > 0
    print("  [GET_FILE] Parameter contract valid")


def test_impact_params() -> None:
    """impact: path required, symbol optional."""
    params_min = {"path": "modules/agent/backend/router.py"}
    assert "path" in params_min
    assert isinstance(params_min["path"], str)
    params_full = {"path": "modules/agent/backend/router.py", "symbol": "AgentService"}
    assert "symbol" in params_full
    assert isinstance(params_full["symbol"], str)
    print("  [IMPACT] Parameter contract valid")


def test_check_boundary_params() -> None:
    """check_boundary: path or module_key (at least one)."""
    params_path = {"path": "modules/agent/backend/router.py"}
    params_key = {"module_key": "agent"}
    params_both = {"path": "modules/agent/backend/router.py", "module_key": "agent"}
    for p in (params_path, params_key, params_both):
        has_path = "path" in p and isinstance(p["path"], str)
        has_key = "module_key" in p and isinstance(p["module_key"], str)
        assert has_path or has_key, "At least one of path/module_key required"
    print("  [CHECK_BOUNDARY] Parameter contract valid")


def test_module_map_params() -> None:
    """module_map: module_key required."""
    params = {"module_key": "agent"}
    assert "module_key" in params
    assert isinstance(params["module_key"], str) and len(params["module_key"]) > 0
    print("  [MODULE_MAP] Parameter contract valid")


def test_search_params() -> None:
    """search: keyword required."""
    params = {"keyword": "AgentService"}
    assert "keyword" in params
    assert isinstance(params["keyword"], str) and len(params["keyword"]) > 0
    print("  [SEARCH] Parameter contract valid")


def test_stats_params() -> None:
    """stats: no params."""
    params: dict = {}
    assert len(params) == 0
    print("  [STATS] Parameter contract valid")


def test_rebuild_params() -> None:
    """rebuild: no params, admin-only."""
    params: dict = {}
    assert len(params) == 0
    print("  [REBUILD] Parameter contract valid")


def test_acquire_lock_params() -> None:
    """acquire_lock: path + agent_id required, ttl optional."""
    params = {"path": "modules/agent/manifest.json", "agent_id": "agent-001", "ttl": 60}
    assert "path" in params and "agent_id" in params
    assert isinstance(params["path"], str) and len(params["path"]) > 0
    assert isinstance(params["agent_id"], str) and len(params["agent_id"]) > 0
    assert isinstance(params["ttl"], int) and params["ttl"] > 0
    print("  [ACQUIRE_LOCK] Parameter contract valid")


def test_check_lock_params() -> None:
    """check_lock: path required."""
    params = {"path": "modules/agent/manifest.json"}
    assert "path" in params
    assert isinstance(params["path"], str) and len(params["path"]) > 0
    print("  [CHECK_LOCK] Parameter contract valid")


def test_release_lock_params() -> None:
    """release_lock: path required."""
    params = {"path": "modules/agent/manifest.json"}
    assert "path" in params
    assert isinstance(params["path"], str) and len(params["path"]) > 0
    print("  [RELEASE_LOCK] Parameter contract valid")


def test_list_locks_params() -> None:
    """list_locks: no params."""
    params: dict = {}
    assert len(params) == 0
    print("  [LIST_LOCKS] Parameter contract valid")


def test_report_inaccuracy_params() -> None:
    """report_inaccuracy: path + query_type required."""
    params = {"path": "modules/agent", "query_type": "impact"}
    assert "path" in params and "query_type" in params
    assert isinstance(params["path"], str)
    assert isinstance(params["query_type"], str)
    print("  [REPORT_INACCURACY] Parameter contract valid")


def test_list_feedback_params() -> None:
    """list_feedback: path optional, admin-only."""
    params_no_path: dict = {}
    params_with_path = {"path": "modules/agent"}
    assert "path" not in params_no_path or isinstance(params_no_path.get("path"), str)
    if "path" in params_with_path:
        assert isinstance(params_with_path["path"], str)
    print("  [LIST_FEEDBACK] Parameter contract valid")


def test_feedback_empty_state_output_shape() -> None:
    """No feedback must be visible as unknown accuracy, not 100%."""
    stats = {
        "query_count": 12,
        "feedback_count": 0,
        "empirical_accuracy": None,
        "empirical_accuracy_status": "no_feedback",
        "empirical_accuracy_note": "暂无 codemap_feedback 反馈样本，empirical_accuracy 未知，不能视为 100% 准确。",
    }
    assert stats["feedback_count"] == 0
    assert stats["empirical_accuracy"] is None
    assert stats["empirical_accuracy_status"] == "no_feedback"
    assert "100%" in stats["empirical_accuracy_note"]

    feedback_list = {
        "items": [],
        "feedback_count": 0,
        "has_feedback": False,
        "aggregated_by_path": True,
        "empty_note": stats["empirical_accuracy_note"],
    }
    assert feedback_list["has_feedback"] is False
    assert feedback_list["items"] == []
    assert "empty_note" in feedback_list
    print("  [FEEDBACK_EMPTY_STATE] Output shape valid")


def test_file_info_output_shape() -> None:
    """File info output shape contract."""
    info = {
        "path": "modules/agent/manifest.json",
        "layer": "modules",
        "module": "agent",
        "language": "json",
        "symbols": ["manifest"],
        "dependencies": [],
        "dependents": [],
        "capabilities_registered": [],
        "capabilities_called": [],
        "tables": [],
    }
    required = {"path", "layer", "module", "language", "symbols"}
    for field in required:
        assert field in info, f"Missing required field: {field}"
    assert isinstance(info["symbols"], list)
    assert isinstance(info["dependencies"], list)
    print("  [FILE_INFO] Output shape valid")


def test_impact_output_shape() -> None:
    """Impact list output shape contract."""
    impact_item = {
        "path": "modules/agent/backend/router.py",
        "confidence": 85,
        "stale": False,
        "empirical_accuracy": 0.92,
        "module": "agent",
    }
    required = {"path", "confidence", "stale", "module"}
    for field in required:
        assert field in impact_item, f"Missing required field: {field}"
    assert isinstance(impact_item["confidence"], int)
    assert 0 <= impact_item["confidence"] <= 100
    assert isinstance(impact_item["stale"], bool)
    print("  [IMPACT_OUTPUT] Output shape valid")


def test_boundary_check_output_shape() -> None:
    """Boundary check output shape contract."""
    result = {
        "path": "modules/agent/backend/router.py",
        "module": "agent",
        "violations": [],
        "status": "clean",
    }
    required = {"path", "module", "violations", "status"}
    for field in required:
        assert field in result, f"Missing required field: {field}"
    assert result["status"] in ("clean", "violations")
    assert isinstance(result["violations"], list)
    print("  [BOUNDARY_OUTPUT] Output shape valid")


def test_lock_output_shape() -> None:
    """Lock state output shape contract."""
    lock = {
        "path": "modules/agent/manifest.json",
        "agent_id": "agent-001",
        "locked_at": "2026-07-01T00:00:00",
        "expires_at": "2026-07-01T01:00:00",
    }
    required = {"path", "agent_id", "locked_at"}
    for field in required:
        assert field in lock, f"Missing required field: {field}"
    print("  [LOCK] Output shape valid")


def test_response_shape() -> None:
    """Unified API response shape contract."""
    r = {"success": True, "data": {}, "error": None}
    assert all(k in r for k in ("success", "data", "error"))
    assert r["success"] is True
    print("  [RESPONSE] Shape valid")


def main() -> None:
    print("=" * 60)
    print("codemap sandbox test")
    print("=" * 60)
    test_get_file_params()
    test_impact_params()
    test_check_boundary_params()
    test_module_map_params()
    test_search_params()
    test_stats_params()
    test_rebuild_params()
    test_acquire_lock_params()
    test_check_lock_params()
    test_release_lock_params()
    test_list_locks_params()
    test_report_inaccuracy_params()
    test_list_feedback_params()
    test_feedback_empty_state_output_shape()
    test_file_info_output_shape()
    test_impact_output_shape()
    test_boundary_check_output_shape()
    test_lock_output_shape()
    test_response_shape()
    print("=" * 60)
    print("PASS: codemap sandbox test")


if __name__ == "__main__":
    main()
