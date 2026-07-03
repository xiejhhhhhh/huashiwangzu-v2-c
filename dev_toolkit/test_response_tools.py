import json

from dev_toolkit.response_shaping import ResponseShapeOptions, shape_response


def _sample_payload() -> dict:
    return {
        "status_code": 200,
        "data": {
            "success": True,
            "data": {
                "summary": {"total": 5, "open": 3},
                "problem_queue": [
                    {"id": 1, "title": "a"},
                    {"id": 2, "title": "b"},
                    {"id": 3, "title": "c"},
                    {"id": 4, "title": "d"},
                ],
            },
            "error": None,
        },
        "target": {"module": "knowledge", "action": "classify_pipeline_debt"},
    }


def test_shape_response_keeps_default_payload_unchanged() -> None:
    payload = _sample_payload()

    shaped = shape_response(payload)

    assert shaped == payload
    assert "response_meta" not in shaped


def test_shape_response_selects_dotted_path() -> None:
    shaped = shape_response(
        _sample_payload(),
        ResponseShapeOptions(selector="data.data.summary"),
    )

    assert shaped["status_code"] == 200
    assert shaped["target"] == {"module": "knowledge", "action": "classify_pipeline_debt"}
    assert shaped["upstream_success"] is True
    assert shaped["data"] == {"total": 5, "open": 3}
    assert shaped["response_meta"] == {
        "truncated": False,
        "selected_path": "data.data.summary",
        "omitted_counts": {},
    }


def test_shape_response_trims_lists_by_max_items() -> None:
    shaped = shape_response(
        _sample_payload(),
        ResponseShapeOptions(selector="data.data.problem_queue", max_items=2),
    )

    assert shaped["data"] == [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}]
    assert shaped["response_meta"]["truncated"] is True
    assert shaped["response_meta"]["omitted_counts"] == {"data.data.problem_queue": 2}


def test_shape_response_trims_to_max_bytes_with_valid_json() -> None:
    payload = _sample_payload()
    payload["data"]["data"]["problem_queue"] = [
        {"id": index, "body": "x" * 1000}
        for index in range(20)
    ]

    shaped = shape_response(payload, ResponseShapeOptions(max_bytes=700))
    encoded = json.dumps(shaped, ensure_ascii=False, indent=2).encode("utf-8")

    assert len(encoded) <= 700
    assert shaped["status_code"] == 200
    assert shaped["target"]["module"] == "knowledge"
    assert shaped["response_meta"]["truncated"] is True
    assert shaped["data"]["_truncated"] is True


def test_shape_response_invalid_selector_warns_without_crashing() -> None:
    shaped = shape_response(
        _sample_payload(),
        ResponseShapeOptions(selector="data.data.missing", max_items=1),
    )

    assert shaped["status_code"] == 200
    assert shaped["data"]["success"] is True
    assert shaped["response_meta"]["selected_path"] is None
    assert shaped["response_meta"]["warnings"] == ["selector not found at data.data.missing"]
