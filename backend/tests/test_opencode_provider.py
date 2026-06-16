import json

from app.services.agent.gateway.stream_parse import (
    error_message,
    extract_stream_payload,
)


def test_extract_stream_payload_accepts_sse_data() -> None:
    chunk = '{"choices":[{"delta":{"content":"hi"}}]}'
    assert extract_stream_payload(f"data: {chunk}") == chunk


def test_extract_stream_payload_accepts_raw_json_line() -> None:
    chunk = '{"choices":[{"delta":{"content":"hi"}}]}'
    assert extract_stream_payload(chunk) == chunk


def test_extract_stream_payload_ignores_event_lines() -> None:
    assert extract_stream_payload("event: ping") is None
    assert extract_stream_payload(": keepalive") is None


def test_error_message_maps_auth_failure() -> None:
    body = json.dumps({"error": {"message": "bad key"}}).encode()
    assert "鉴权失败" in error_message(401, body)
