from app.services.agent.tool_audit import (
    build_assistant_tool_calls,
    make_result_summary,
    normalize_tool_call,
    parse_text_tool_calls,
)
from app.services.agent.message_store import serialize_message
from app.services.agent.tools.registry import ToolResult
from app.services.agent.tools.register_all import register_all_tools
from app.services.agent.tools.registry import tool_registry


def test_parse_text_tool_calls_uses_dict_arguments():
    text = '{"name":"search_knowledge","arguments":{"query":"清颜","top_k":5}}'
    calls = parse_text_tool_calls(text)
    assert calls[0]["function"]["name"] == "search_knowledge"
    assert calls[0]["function"]["arguments"] == {"query": "清颜", "top_k": 5}


def test_normalize_tool_call_accepts_json_string_arguments():
    call = {"function": {"name": "search_knowledge", "arguments": '{"query":"清颜"}'}}
    name, args = normalize_tool_call(call)
    assert name == "search_knowledge"
    assert args == {"query": "清颜"}


def test_build_assistant_tool_calls_keeps_normalized_arguments():
    call = {"function": {"name": "search_knowledge", "arguments": '{"query":"清颜"}'}}
    result = build_assistant_tool_calls([call])
    assert result[0]["function"]["arguments"] == {"query": "清颜"}


def test_make_search_result_summary_is_compact():
    result = ToolResult(data={"items": [{"fusion_id": 37}, {"fusion_id": 40}]})
    assert make_result_summary("search_knowledge", result) == "命中2条，fusion_id=[37,40]"


def test_serialize_message_uses_snake_case_tools_called():
    msg = type("Msg", (), {
        "id": 1,
        "role": "assistant",
        "content": "答案",
        "thinking": "",
        "tools_called": [{"name": "search_knowledge"}],
        "created_at": None,
    })()
    data = serialize_message(msg)
    assert data["tools_called"] == [{"name": "search_knowledge"}]
    assert "toolsCalled" not in data


def test_register_all_tools_includes_v1_parity_tools():
    register_all_tools()
    names = {item["name"] for item in tool_registry.list_tools()}
    assert {
        "search_knowledge",
        "get_page_fusion",
        "read_chunk",
        "read_entity",
        "read_evidence",
        "read_file",
        "read_graph_context",
        "read_pending_candidates",
        "read_latest_evaluation",
        "read_system_status",
    }.issubset(names)
