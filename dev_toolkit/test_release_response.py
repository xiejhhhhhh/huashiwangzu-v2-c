from dev_toolkit.release_response import build_release_gate_response


def test_release_gate_response_does_not_map_debt_to_clean_success() -> None:
    output = 'human\nRELEASE_GATE_JSON: {"verdict": "PASS_WITH_DEBT", "has_debt": true}\n'
    result = build_release_gate_response(
        output=output,
        returncode=0,
        skip_ui=True,
        duration_seconds=1.2345,
    )

    assert result["success"] is False
    assert result["clean_pass"] is False
    assert result["clean_release_ready"] is False
    assert result["release_safe"] is True
    assert result["has_debt"] is True
    assert result["ui_skipped"] is True
    assert result["verdict"] == "PASS_WITH_DEBT"


def test_release_gate_response_forces_skip_ui_pass_to_debt() -> None:
    output = 'human\nRELEASE_GATE_JSON: {"verdict": "PASS", "clean_pass": true}\n'
    result = build_release_gate_response(
        output=output,
        returncode=0,
        skip_ui=True,
        duration_seconds=1.0,
    )

    assert result["success"] is False
    assert result["clean_pass"] is False
    assert result["clean_release_ready"] is False
    assert result["release_safe"] is True
    assert result["has_debt"] is True
    assert result["ui_skipped"] is True
    assert result["gate_mode"] == "backend_preflight"
    assert result["verdict"] == "PASS_WITH_DEBT"


def test_release_gate_response_fails_closed_without_machine_json() -> None:
    result = build_release_gate_response(
        output="human only\nlooks fine\n",
        returncode=0,
        skip_ui=False,
        duration_seconds=0.5,
    )

    assert result["success"] is False
    assert result["clean_pass"] is False
    assert result["clean_release_ready"] is False
    assert result["release_safe"] is False
    assert result["verdict"] == "INVALID_GATE_OUTPUT"
    assert result["invalid_output"] is True
    assert "human only" in result["output_tail"]
