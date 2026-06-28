import pytest
from app.gateway.protocol import GatewayProtocolError, normalize_openai_messages, normalize_openai_tools


def test_normalize_accepts_complete_parallel_tool_results() -> None:
    messages = [
        {"role": "user", "content": "查两个信息"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_a", "type": "function", "function": {"name": "get_weather", "arguments": {"city": "北京"}}},
            {"id": "call_b", "type": "function", "function": {"name": "get_time", "arguments": {"city": "东京"}}},
        ]},
        {"role": "tool", "tool_call_id": "call_a", "content": "晴"},
        {"role": "tool", "tool_call_id": "call_b", "content": "10:00"},
        {"role": "user", "content": "总结"},
    ]
    normalized = normalize_openai_messages(messages)
    tool_calls = normalized[1]["tool_calls"]
    assert len(tool_calls) == 2
    assert tool_calls[0]["function"]["arguments"] == '{"city": "北京"}'


def test_normalize_rejects_missing_tool_result() -> None:
    messages = [
        {"role": "user", "content": "查两个信息"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_a", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}},
            {"id": "call_b", "type": "function", "function": {"name": "get_time", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_a", "content": "晴"},
    ]
    with pytest.raises(GatewayProtocolError, match="missing matching tool results"):
        normalize_openai_messages(messages)


def test_normalize_rejects_orphan_tool_message() -> None:
    with pytest.raises(GatewayProtocolError, match="orphan tool message"):
        normalize_openai_messages([{"role": "tool", "tool_call_id": "call_a", "content": "孤儿结果"}])


def test_normalize_tools_accepts_internal_shorthand() -> None:
    tools = [{"name": "search", "description": "Search", "parameters": {"type": "object"}}]
    normalized = normalize_openai_tools(tools)
    assert normalized == [{
        "type": "function",
        "function": {"name": "search", "description": "Search", "parameters": {"type": "object"}},
    }]
