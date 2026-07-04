from app.services import task_worker


def test_task_worker_treats_skipped_as_successful_noop() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "status": "skipped",
        "reason": "source_file_deleted",
    })

    assert failed is False
    assert error is None


def test_task_worker_treats_failed_status_as_failure() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "status": "failed",
        "error": "slow tool failed",
    })

    assert failed is True
    assert error == "slow tool failed"


def test_task_worker_treats_success_false_as_failure() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "success": False,
        "error": "agent execution failed",
    })

    assert failed is True
    assert error == "agent execution failed"


def test_task_worker_treats_nested_success_false_as_failure() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "success": True,
        "data": {"success": False, "error": "nested failed"},
    })

    assert failed is True
    assert error == "nested failed"


def test_task_worker_treats_legacy_code_nonzero_as_failure() -> None:
    failed, error = task_worker._result_is_semantic_failure({
        "code": 1,
        "msg": "legacy tool failed",
    })

    assert failed is True
    assert error == "legacy tool failed"
