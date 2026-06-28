"""Tests for ContentGate — unified content cleaning and classification."""

import importlib.util
import sys
import types
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[3]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

# Stub engine module for stream_emitter import compatibility
engine_module = types.ModuleType("modules.agent.backend.engine.engine")
engine_module.chat_stream_with_degradation_chain = lambda *a, **kw: (_ for _ in ())
failure_module = types.ModuleType("modules.agent.backend.engine.failure_diagnostics")
failure_module.record_failure = lambda *a, **kw: None
sys.modules["modules.agent.backend.engine.engine"] = engine_module
sys.modules["modules.agent.backend.engine.failure_diagnostics"] = failure_module

CONTENT_GATE_PATH = REPO_DIR / "modules/agent/backend/runtime/content_gate.py"
spec = importlib.util.spec_from_file_location("modules.agent.backend.runtime.content_gate", CONTENT_GATE_PATH)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

process = gate.process
parse_inline_tool_calls = gate.parse_inline_tool_calls
final_clean_content = gate.final_clean_content
looks_like_unfinished_tool_intent = gate.looks_like_unfinished_tool_intent
user_safe_error_message = gate.user_safe_error_message
MODEL_UNAVAILABLE_MESSAGE = gate.MODEL_UNAVAILABLE_MESSAGE


def test_plain_text_passthrough():
    r = process("你好，今天天气不错。")
    assert r.has_visible_text is True
    assert r.is_empty is False
    assert r.is_xml_only is False
    assert r.clean_text == "你好，今天天气不错。"
    assert r.extracted_tool_calls_count == 0


def test_strips_dsml_tool_calls():
    raw = '<DSML><tool_calls><invoke name="skill_use"><parameter name="name" string="true">web-search</parameter></invoke></tool_calls></DSML>'
    r = process(raw)
    assert r.has_visible_text is False
    assert r.is_xml_only is True
    assert r.clean_text == ""
    assert r.extracted_tool_calls_count == 1


def test_mixed_text_and_tool_calls():
    raw = '答案是42。<invoke name="calculate"><parameter name="x" string="false">6</parameter><parameter name="y" string="false">7</parameter></invoke>'
    r = process(raw)
    assert r.has_visible_text is True
    assert r.clean_text == "答案是42。"
    assert r.extracted_tool_calls_count == 1


def test_multiple_tool_calls():
    raw = (
        '<invoke name="search"><parameter name="q" string="true">python</parameter></invoke>'
        '<invoke name="fetch"><parameter name="url" string="true">https://example.com</parameter></invoke>'
    )
    r = process(raw)
    assert r.is_xml_only is True
    assert r.clean_text == ""
    assert r.extracted_tool_calls_count == 2


def test_unfinished_tool_intent_detected():
    r = process("这个问题我帮你联网查一下最新信息。")
    assert r.unfinished_tool_intent is True
    assert r.has_visible_text is True
    assert r.extracted_tool_calls_count == 0
    assert r.blocked_reason == "unfinished_tool_intent"


def test_normal_answer_with_search_context():
    r = process("根据搜索结果，巨量千川后台可以在工具里的创意营销榜查看对标视频。")
    assert r.unfinished_tool_intent is False
    assert r.has_visible_text is True


def test_empty_input():
    r = process("")
    assert r.is_empty is True
    assert r.blocked_reason == "empty_input"


def test_whitespace_only():
    r = process("   \n\n  ")
    assert r.is_empty is True
    assert r.blocked_reason == "cleaned_to_empty"


def test_backward_compat_parse_inline_tool_calls():
    raw = '<invoke name="test"><parameter name="x" string="false">1</parameter></invoke>'
    clean, calls = parse_inline_tool_calls(raw)
    assert clean == ""
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "test"


def test_backward_compat_final_clean_content():
    raw = 'hello<invoke name="x"><parameter name="y" string="true">z</parameter></invoke>'
    clean = final_clean_content(raw)
    assert clean == "hello"


def test_backward_compat_looks_like_unfinished():
    assert looks_like_unfinished_tool_intent("我来联网查一下") is True
    assert looks_like_unfinished_tool_intent("正常答案在这里") is False


def test_normalize_pipe_variants():
    # Full-width vertical bar prefix
    raw = 'text |invoke name="test"><parameter name="a" string="true">b</parameter></|invoke>'
    r = process(raw)
    assert r.has_visible_text is True
    assert r.extracted_tool_calls_count == 1


def test_dsml_angle_bracket_variant():
    raw = '<DSML><tool_calls><invoke name="web_search"><parameter name="query" string="true">hello</parameter></invoke></tool_calls></DSML>'
    r = process(raw)
    assert r.is_xml_only is True
    assert r.extracted_tool_calls_count == 1


def test_string_false_converts_number():
    raw = '<invoke name="calc"><parameter name="val" string="false">42</parameter></invoke>after'
    r = process(raw)
    assert r.clean_text == "after"
    assert r.extracted_tool_calls_count == 1
    args = r.inline_tool_calls[0]["function"]["arguments"]
    assert args["val"] == 42
    assert isinstance(args["val"], int)


def test_user_safe_error_hides_model_connection_details():
    assert user_safe_error_message("Model error: All connection attempts failed") == MODEL_UNAVAILABLE_MESSAGE
    assert user_safe_error_message("(stream error: ConnectTimeout)") == MODEL_UNAVAILABLE_MESSAGE


def test_user_safe_error_keeps_short_business_message():
    assert user_safe_error_message("模型表示需要查询资料，但连续没有发起工具调用。") == "模型表示需要查询资料，但连续没有发起工具调用。"


def test_best_path_summary_removed_from_visible_content():
    raw = (
        "答案正文。\n\n"
        "最佳路径总结：\n"
        "在巨量千川后台 → 工具 → 素材分析，选择对应类目和时间范围。\n\n"
        "📎 来源：\n"
        "- [素材分析产品介绍](https://example.com/a)"
    )
    assert "最佳路径总结" not in final_clean_content(raw)
    assert "📎 来源" not in final_clean_content(raw)
    assert final_clean_content(raw) == "答案正文。"


def test_extracts_success_path_and_inline_references():
    raw = (
        "<p><strong>最佳路径总结：</strong><br>在巨量千川后台 → <strong>工具</strong> → <strong>素材分析</strong>。</p>"
        "<p>📎 来源：</p>"
        "<ul><li><a href=\"https://www.zhihu.com/question/548102282\">巨量千川怎么查看同行的跑量素材创意？ - 知乎</a></li>"
        "<li><a href=\"https://qianchuan.jinritemai.com/support/content/127803\">素材分析产品介绍 - 巨量千川规则中心</a></li></ul>"
    )
    assert gate.extract_success_path(raw) == "在巨量千川后台 → 工具 → 素材分析。"
    refs = gate.extract_inline_references(raw)
    assert [ref["title"] for ref in refs] == [
        "巨量千川怎么查看同行的跑量素材创意？ - 知乎",
        "素材分析产品介绍 - 巨量千川规则中心",
    ]
    assert [ref["url"] for ref in refs] == [
        "https://www.zhihu.com/question/548102282",
        "https://qianchuan.jinritemai.com/support/content/127803",
    ]
