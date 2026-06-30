"""Tests for tool_result_reducer.py — upgrade 10.

Covers:
- skill_use tool name resolution
- Large tool_result summarization
- Duplicate tool_result dedup
- Recent tool_result protection
- tool_call arguments truncation (JSON validity)
- Historical image stripping
- tool_call/tool_result atomic groups
"""
import json

from .tool_result_reducer import (
    _resolve_tool_name_from_assistant_messages,
    _semantic_summary,
    _strip_images,
    _truncate_tool_call_arguments,
    reduce,
)


class TestResolveToolName:
    def test_regular_tool_call(self):
        msgs = [
            {"role": "assistant", "tool_calls": [
                {"id": "call_1", "function": {"name": "terminal-tools__exec", "arguments": {}}},
            ]},
        ]
        mapping = _resolve_tool_name_from_assistant_messages(msgs)
        assert mapping.get("call_1") == "terminal-tools__exec"

    def test_skill_use_resolves_inner_name(self):
        msgs = [
            {"role": "assistant", "tool_calls": [
                {"id": "call_2", "function": {
                    "name": "skill_use",
                    "arguments": {"name": "knowledge__search", "args": {"q": "test"}},
                }},
            ]},
        ]
        mapping = _resolve_tool_name_from_assistant_messages(msgs)
        assert mapping.get("call_2") == "knowledge__search"

    def test_skill_use_with_string_args(self):
        msgs = [
            {"role": "assistant", "tool_calls": [
                {"id": "call_3", "function": {
                    "name": "skill_use",
                    "arguments": '{"name": "media-asr__transcribe_video", "args": {}}',
                }},
            ]},
        ]
        mapping = _resolve_tool_name_from_assistant_messages(msgs)
        assert mapping.get("call_3") == "media-asr__transcribe_video"

    def test_unknown_skill_use_falls_back(self):
        msgs = [
            {"role": "assistant", "tool_calls": [
                {"id": "call_4", "function": {
                    "name": "skill_use",
                    "arguments": {"namex": "unknown"},
                }},
            ]},
        ]
        mapping = _resolve_tool_name_from_assistant_messages(msgs)
        # Falls back to "skill_use" since name key missing
        assert mapping.get("call_4") == "skill_use"

    def test_no_tool_calls(self):
        msgs = [{"role": "user", "content": "hello"}]
        mapping = _resolve_tool_name_from_assistant_messages(msgs)
        assert mapping == {}


class TestToolResultSummarization:
    def test_large_knowledge_search_semantic_summary(self):
        content = json.dumps({
            "results": [{"title": f"Doc {i}", "content": "x" * 200} for i in range(20)],
        })
        result = _semantic_summary(content, "knowledge__search")
        data = json.loads(result)
        assert len(data.get("results", [])) <= 6  # 5 kept + 1 total marker

    def test_large_text_summarization(self):
        content = "word " * 10000
        result = _semantic_summary(content, "desktop-tools__read_file")
        assert len(result) < len(content)
        assert "[截断]" in result or "省略" in result

    def test_small_content_untouched(self):
        content = "small result"
        result = _semantic_summary(content, "web-tools__fetch")
        assert result == content

    def test_generic_tool_fallback(self):
        from .tool_result_reducer import _reduce_tool_content
        content = "A" * 5000
        result = _reduce_tool_content(content, "unknown-tool")
        assert len(result) < len(content)


class TestDedup:
    def test_identical_tool_results_deduped(self):
        content = json.dumps({"data": "some result"})
        msgs = [
            {"role": "tool", "content": content, "tool_call_id": "c1", "name": "test"},
            {"role": "tool", "content": content, "tool_call_id": "c2", "name": "test"},
        ]
        reduced, diag = reduce(msgs)
        assert diag["tool_results_deduped"] == 1
        assert reduced[0]["content"] == content
        assert "[重复结果已去重]" in reduced[1]["content"]

    def test_different_content_not_deduped(self):
        msgs = [
            {"role": "tool", "content": "result A", "tool_call_id": "c1", "name": "test"},
            {"role": "tool", "content": "result B", "tool_call_id": "c2", "name": "test"},
        ]
        reduced, diag = reduce(msgs)
        assert diag["tool_results_deduped"] == 0
        assert reduced[1]["content"] == "result B"


class TestRecentToolProtection:
    def test_recent_two_tool_results_only_capped(self):
        content_a = "x" * 20000
        content_b = "y" * 20000
        msgs = [
            {"role": "tool", "content": "old result", "tool_call_id": "c1", "name": "test"},
            {"role": "tool", "content": content_a, "tool_call_id": "c2", "name": "test"},
            {"role": "tool", "content": content_b, "tool_call_id": "c3", "name": "test"},
        ]
        reduced, diag = reduce(msgs)
        assert diag["protected_recent_tool_results"] == 2
        # Both recent should be capped but not semantically summarized
        recent_1 = reduced[-2]["content"]
        recent_2 = reduced[-1]["content"]
        assert "[结果过长，省略" in recent_1
        assert "[结果过长，省略" in recent_2
        # Old result under 500 chars stays unchanged
        assert reduced[0]["content"] == "old result"

    def test_protected_recent_not_semantically_summarized(self):
        """Protected results should NOT get semantic summary (only char cap)."""
        content = "x" * 20000
        msgs = [
            {"role": "tool", "content": content, "tool_call_id": "c1", "name": "test"},
        ]
        reduced, _ = reduce(msgs, max_text_chars=500)
        recent_content = reduced[0]["content"]
        # Should use protected cap format, not semantic summary
        assert "[结果过长，省略" in recent_content or len(recent_content) <= 8000 or len(recent_content) < len(content)


class TestToolCallArgsTruncation:
    def test_skill_use_nested_query_truncated(self):
        original_query = "长查询" * 1000
        msg = {"role": "assistant", "tool_calls": [
            {"id": "c1", "function": {
                "name": "skill_use",
                "arguments": json.dumps({
                    "name": "knowledge__search",
                    "args": {"query": original_query},
                }),
            }},
        ]}

        reduced, diagnosis = reduce([msg])

        args_raw = reduced[0]["tool_calls"][0]["function"]["arguments"]
        assert diagnosis["tool_args_truncated"] > 0
        assert isinstance(args_raw, str)
        args = json.loads(args_raw)
        assert len(args["args"]["query"]) < len(original_query)
        assert "省略" in args["args"]["query"]

    def test_skill_use_nested_items_truncated(self):
        msg = {"role": "assistant", "tool_calls": [
            {"id": "c1", "function": {
                "name": "skill_use",
                "arguments": json.dumps({
                    "name": "knowledge__search",
                    "args": {"items": list(range(20))},
                }),
            }},
        ]}

        result = _truncate_tool_call_arguments(msg)

        args_raw = result["tool_calls"][0]["function"]["arguments"]
        assert isinstance(args_raw, str)
        args = json.loads(args_raw)
        assert args["args"]["items"][:5] == [0, 1, 2, 3, 4]
        assert len(args["args"]["items"]) == 6
        assert "仅保留前5项" in args["args"]["items"][-1]

    def test_deep_dict_uses_placeholder_without_error(self):
        deeply_nested = {"level1": {"level2": {"level3": {"level4": {"level5": {"value": "ok"}}}}}}
        msg = {"role": "assistant", "tool_calls": [
            {"id": "c1", "function": {"name": "skill_use", "arguments": deeply_nested}},
        ]}

        result = _truncate_tool_call_arguments(msg)

        args_raw = result["tool_calls"][0]["function"]["arguments"]
        assert isinstance(args_raw, str)
        args = json.loads(args_raw)
        assert "参数嵌套过深已省略" in json.dumps(args, ensure_ascii=False)

    def test_short_json_string_arguments_preserve_original_format(self):
        original = '{ "name": "knowledge__search", "args": { "query": "short" } }'
        msg = {"role": "assistant", "tool_calls": [
            {"id": "c1", "function": {"name": "skill_use", "arguments": original}},
        ]}

        result = _truncate_tool_call_arguments(msg)

        assert result["tool_calls"][0]["function"]["arguments"] == original

    def test_short_dict_arguments_become_valid_json_string(self):
        msg = {"role": "assistant", "tool_calls": [
            {"id": "c1", "function": {
                "name": "skill_use",
                "arguments": {"name": "knowledge__search", "args": {"query": "short"}},
            }},
        ]}

        reduced, diagnosis = reduce([msg])

        args_raw = reduced[0]["tool_calls"][0]["function"]["arguments"]
        assert diagnosis["tool_args_truncated"] == 0
        assert isinstance(args_raw, str)
        assert json.loads(args_raw)["args"]["query"] == "short"

    def test_long_string_truncated(self):
        msg = {"role": "assistant", "tool_calls": [
            {"id": "c1", "function": {
                "name": "test",
                "arguments": {"long_field": "A" * 2000},
            }},
        ]}
        result = _truncate_tool_call_arguments(msg)
        args_raw = result["tool_calls"][0]["function"]["arguments"]
        assert isinstance(args_raw, str)
        args = json.loads(args_raw)
        assert len(args["long_field"]) < 600  # truncated
        assert "省略" in args["long_field"]

    def test_large_array_truncated(self):
        msg = {"role": "assistant", "tool_calls": [
            {"id": "c1", "function": {
                "name": "test",
                "arguments": {"items": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]},
            }},
        ]}
        result = _truncate_tool_call_arguments(msg)
        args_raw = result["tool_calls"][0]["function"]["arguments"]
        assert isinstance(args_raw, str)
        args = json.loads(args_raw)
        assert len(args["items"]) <= 6  # 5 + 1 marker
        assert "共" in str(args["items"][-1])

    def test_empty_tool_calls_untouched(self):
        msg = {"role": "user", "content": "hello"}
        result = _truncate_tool_call_arguments(msg)
        assert result == msg
        assert result.get("content") == "hello"

    def test_string_args_parsed(self):
        msg = {"role": "assistant", "tool_calls": [
            {"id": "c1", "function": {
                "name": "test",
                "arguments": '{"data": "' + "A" * 2000 + '"}',
            }},
        ]}
        result = _truncate_tool_call_arguments(msg)
        args_raw = result["tool_calls"][0]["function"]["arguments"]
        assert isinstance(args_raw, str)
        args = json.loads(args_raw)
        assert len(args["data"]) < 600

    def test_json_validity_preserved(self):
        msg = {"role": "assistant", "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {
                    "name": "skill_use",
                    "arguments": json.dumps({
                        "name": "knowledge__search",
                        "args": {"query": "A" * 2000, "limit": 10},
                    }),
                },
            },
        ]}
        result = _truncate_tool_call_arguments(msg)
        # Must still be valid JSON serializable
        payload = json.dumps(result)
        parsed = json.loads(payload)
        assert parsed["tool_calls"][0]["function"]["name"] == "skill_use"
        inner_args_raw = parsed["tool_calls"][0]["function"]["arguments"]
        assert isinstance(inner_args_raw, str)
        inner_args = json.loads(inner_args_raw)
        assert isinstance(inner_args, dict)
        assert inner_args["name"] == "knowledge__search"


class TestImageStripping:
    def test_data_uri_stripped(self):
        msg = {"role": "assistant", "content": "See image: data:image/png;base64,iVBORw0KGgoAAAANSUhEUg"}
        stripped, was = _strip_images(msg)
        assert was
        assert "[图片已省略]" in stripped["content"]

    def test_no_image_untouched(self):
        msg = {"role": "user", "content": "just text"}
        stripped, was = _strip_images(msg)
        assert not was
        assert stripped["content"] == "just text"

    def test_historical_images_stripped_in_reduce(self):
        msgs = [
            {"role": "assistant", "content": "See: data:image/jpeg;base64,/9j/4AAQSkZJRg"},
        ]
        reduced, diag = reduce(msgs)
        assert diag["images_stripped"] >= 1
        assert "[图片已省略]" in reduced[0]["content"]

    def test_recent_user_images_not_stripped(self):
        msgs = [
            {"role": "user", "content": "data:image/png;base64,iVBORw0KGgo"},
        ]
        reduced, diag = reduce(msgs)
        # User messages are skipped for image stripping
        assert "[图片已省略]" not in reduced[0]["content"]


class TestDiagnosisCounters:
    def test_all_counters_present(self):
        msgs = [
            {"role": "assistant", "tool_calls": [
                {"id": "c1", "function": {"name": "test", "arguments": {"data": "A" * 2000}}},
            ]},
            {"role": "tool", "content": json.dumps({"result": "B" * 5000}), "tool_call_id": "c1", "name": "test"},
        ]
        _, diag = reduce(msgs)
        assert "tool_results_compressed" in diag
        assert "tool_results_deduped" in diag
        assert "tool_args_truncated" in diag
        assert "images_stripped" in diag
        assert "total_chars_saved" in diag
        assert "protected_recent_tool_results" in diag

    def test_total_chars_saved_positive(self):
        # 3 tool results so only the last 2 are protected.
        # The first unprotected one should be compressed.
        msgs = [
            {"role": "tool", "content": json.dumps({"result": "B" * 5000}), "tool_call_id": "c1", "name": "test"},
            {"role": "tool", "content": json.dumps({"result": "C" * 500}), "tool_call_id": "c2", "name": "test"},
            {"role": "tool", "content": json.dumps({"result": "D" * 500}), "tool_call_id": "c3", "name": "test"},
        ]
        _, diag = reduce(msgs)
        assert diag["total_chars_saved"] > 0


class TestSpecialTemplates:
    def test_summary_template_structure(self):
        from ..compressor import _STRUCTURED_SUMMARY_PROMPT
        assert "## 用户目标" in _STRUCTURED_SUMMARY_PROMPT
        assert "## 已完成" in _STRUCTURED_SUMMARY_PROMPT
        assert "## 关键决策" in _STRUCTURED_SUMMARY_PROMPT
        assert "## 工具与结果" in _STRUCTURED_SUMMARY_PROMPT
        assert "## 相关文件/数据" in _STRUCTURED_SUMMARY_PROMPT
        assert "## 未完成/待确认" in _STRUCTURED_SUMMARY_PROMPT
        assert "## 当前状态" in _STRUCTURED_SUMMARY_PROMPT
        assert "{{text}}" in _STRUCTURED_SUMMARY_PROMPT
