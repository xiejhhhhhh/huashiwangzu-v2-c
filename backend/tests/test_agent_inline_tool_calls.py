"""Test parse_inline_tool_calls — inline XML tool call detection."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[2] / "modules" / "agent" / "backend" / "services"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from model_client import final_clean_content, parse_inline_tool_calls, recover_tool_calls


class TestParseInlineToolCalls:
    def test_basic_invoke(self):
        content = '你好<invoke name="web-tools__search"><parameter name="q" string="true">天气</parameter></invoke>'
        clean, calls = parse_inline_tool_calls(content)
        assert clean == "你好"
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "web-tools__search"
        assert calls[0]["function"]["arguments"] == {"q": "天气"}

    def test_antml_prefix(self):
        content = '介绍<antml:invoke name="knowledge__search"><antml:parameter name="q">品牌</antml:parameter></antml:invoke>'
        clean, calls = parse_inline_tool_calls(content)
        assert clean == "介绍"
        assert calls[0]["function"]["name"] == "knowledge__search"

    def test_full_width_vertical_bar(self):
        content = '查一下｜invoke name="web-tools__fetch"><｜parameter name="url" string="true">https://example.com</｜parameter></｜invoke>'
        clean, calls = parse_inline_tool_calls(content)
        assert clean == "查一下"
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "web-tools__fetch"
        assert calls[0]["function"]["arguments"] == {"url": "https://example.com"}

    def test_string_false_converts_number(self):
        content = '<invoke name="terminal-tools__exec"><parameter name="command" string="true">ls</parameter><parameter name="timeout" string="false">30</parameter></invoke>'
        clean, calls = parse_inline_tool_calls(content)
        assert calls[0]["function"]["arguments"]["command"] == "ls"
        assert calls[0]["function"]["arguments"]["timeout"] == 30
        assert isinstance(calls[0]["function"]["arguments"]["timeout"], int)

    def test_string_false_converts_bool(self):
        content = '<invoke name="test__flag"><parameter name="enabled" string="false">true</parameter></invoke>'
        clean, calls = parse_inline_tool_calls(content)
        assert calls[0]["function"]["arguments"]["enabled"] is True

    def test_no_inline_calls(self):
        content = "今天天气怎么样？"
        clean, calls = parse_inline_tool_calls(content)
        assert clean == content
        assert calls == []

    def test_multiple_calls(self):
        content = (
            '先查<invoke name="web-tools__search"><parameter name="q">news</parameter></invoke>'
            '再读<invoke name="web-tools__fetch"><parameter name="url">https://x.com</parameter></invoke>'
        )
        clean, calls = parse_inline_tool_calls(content)
        assert clean == "先查再读"
        assert len(calls) == 2
        assert calls[0]["function"]["name"] == "web-tools__search"
        assert calls[1]["function"]["name"] == "web-tools__fetch"

    def test_text_before_and_after(self):
        content = '回答开头。嗯<invoke name="knowledge__search"><parameter name="keyword">产品</parameter></invoke>后面还有内容。'
        clean, calls = parse_inline_tool_calls(content)
        assert "回答开头。嗯" in clean
        assert "后面还有内容。" in clean
        assert "<invoke" not in clean
        assert len(calls) == 1

    def test_case_insensitive(self):
        content = '<INVOKE NAME="TOOL__ACTION"><PARAMETER NAME="X">Y</PARAMETER></INVOKE>'
        clean, calls = parse_inline_tool_calls(content)
        assert calls[0]["function"]["name"] == "TOOL__ACTION"
        assert calls[0]["function"]["arguments"]["X"] == "Y"

    def test_empty_content(self):
        clean, calls = parse_inline_tool_calls("")
        assert clean == ""
        assert calls == []

    def test_none_content(self):
        clean, calls = parse_inline_tool_calls(None)
        assert clean is None
        assert calls == []


class TestFinalCleanContent:
    """Test the final_clean_content safety net."""

    def test_invoke_markup_stripped(self):
        content = '这是正文<invoke name="image-gen__generate"><parameter name="prompt">a cat</parameter></invoke>后面内容'
        cleaned = final_clean_content(content)
        assert "<invoke" not in cleaned
        assert "这是正文" in cleaned
        assert "后面内容" in cleaned

    def test_antml_markup_stripped(self):
        content = '内容<antml:invoke name="tool"><antml:parameter name="x">y</antml:parameter></antml:invoke>结尾'
        cleaned = final_clean_content(content)
        assert "antml:invoke" not in cleaned
        assert "内容" in cleaned
        assert "结尾" in cleaned

    def test_tool_call_container_stripped(self):
        content = '正文<tool_call><invoke name="test"><parameter name="x">1</parameter></invoke></tool_call>完'
        cleaned = final_clean_content(content)
        assert "<tool_call>" not in cleaned
        assert "<invoke" not in cleaned
        assert "正文" in cleaned
        assert "完" in cleaned

    def test_empty_string(self):
        assert final_clean_content("") == ""

    def test_clean_content_unchanged(self):
        content = "这是普通的文本内容，没有工具标记。"
        assert final_clean_content(content) == content

    def test_multiple_newlines_collapsed(self):
        content = "a\n\n\n\n\nb"
        assert final_clean_content(content) == "a\n\nb"

    def test_full_width_markup_stripped(self):
        content = '正文｜invoke name="test__tool"><｜parameter name="x">1</｜parameter></｜invoke>结尾'
        cleaned = final_clean_content(content)
        assert "｜invoke" not in cleaned
        assert "parameter" not in cleaned
        assert cleaned == "正文结尾"


class TestRecoverToolCalls:
    @pytest.mark.asyncio
    async def test_recover_uses_gateway_adapter_shape(self):
        gateway_result = {
            "content": "",
            "thinking": "reasoning",
            "finish_reason": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "web-tools__search",
                    "arguments": '{"q": "天气"}',
                },
            }],
        }
        with patch("model_client.gateway_router.chat", AsyncMock(return_value=gateway_result)) as chat:
            result = await recover_tool_calls(
                messages=[{"role": "user", "content": "查天气"}],
                profile_key="deepseek-v4-flash",
                tools=[{"type": "function", "function": {"name": "web-tools__search"}}],
            )
        chat.assert_awaited_once()
        assert result["thinking"] == "reasoning"
        assert result["finish_reason"] == "tool_calls"
        assert result["tool_calls"][0]["function"]["arguments"] == {"q": "天气"}

    @pytest.mark.asyncio
    async def test_recover_bad_arguments_fallback_to_empty_dict(self):
        gateway_result = {
            "tool_calls": [{
                "id": "call_1",
                "function": {"name": "tool", "arguments": "{bad json}"},
            }],
        }
        with patch("model_client.gateway_router.chat", AsyncMock(return_value=gateway_result)):
            result = await recover_tool_calls([], "deepseek-v4-flash", [])
        assert result["tool_calls"][0]["function"]["arguments"] == {}


class TestHandleSkillUseArgsParsing:
    """Test args string→dict conversion logic (as used in handle_skill_use)."""

    def test_args_is_dict_passes_through(self):
        args = {"prompt": "hello", "size": "1024x1024"}
        # same logic as handle_skill_use
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args) if args.strip() else {}
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}
        assert args == {"prompt": "hello", "size": "1024x1024"}

    def test_args_is_valid_json_string(self):
        args = '{"prompt": "hello", "size": "1024x1024"}'
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args) if args.strip() else {}
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}
        assert args == {"prompt": "hello", "size": "1024x1024"}

    def test_args_is_invalid_json_string_fallback(self):
        args = "{broken json}"
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args) if args.strip() else {}
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}
        assert args == {}

    def test_args_is_empty_string(self):
        args = ""
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args) if args.strip() else {}
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}
        assert args == {}

    def test_args_is_list_fallback(self):
        args = ["not", "a", "dict"]
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args) if args.strip() else {}
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}
        assert args == {}
