"""Tests for model_client inline DSML tool-call fallback."""

import importlib
import sys
import types
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent / "services"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

app_module = types.ModuleType("app")
gateway_package = types.ModuleType("app.gateway")
gateway_router_module = types.ModuleType("app.gateway.router")
gateway_router_module.gateway_router = object()
original_modules = {
    name: sys.modules.get(name)
    for name in ("app", "app.gateway", "app.gateway.router")
}
sys.modules["app"] = app_module
sys.modules["app.gateway"] = gateway_package
sys.modules["app.gateway.router"] = gateway_router_module
try:
    model_client = importlib.import_module("model_client")
finally:
    for name, module in original_modules.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
final_clean_content = model_client.final_clean_content
parse_inline_tool_calls = model_client.parse_inline_tool_calls


DSML_TOOL_CALL = (
    '<｜｜DSML｜｜tool_calls>\n'
    '<｜｜DSML｜｜invoke name="skill_use">\n'
    '<｜｜DSML｜｜parameter name="name" string="true">web-tools__search</｜｜DSML｜｜parameter>\n'
    '<｜｜DSML｜｜parameter name="args" string="false">{"query":"巨量千川 创意灵感 对标视频 行业视频 在哪里找"}</｜｜DSML｜｜parameter>\n'
    '</｜｜DSML｜｜invoke>\n'
    '</｜｜DSML｜｜tool_calls>'
)


def test_parse_dsml_tool_calls_container():
    clean, calls = parse_inline_tool_calls(DSML_TOOL_CALL)

    assert clean == ""
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "skill_use"
    assert calls[0]["function"]["arguments"] == {
        "name": "web-tools__search",
        "args": {"query": "巨量千川 创意灵感 对标视频 行业视频 在哪里找"},
    }


def test_final_clean_content_strips_dsml_tool_calls():
    cleaned = final_clean_content(f"回复前{DSML_TOOL_CALL}回复后")

    assert cleaned == "回复前回复后"
    assert "DSML" not in cleaned
    assert "tool_calls" not in cleaned
    assert "invoke" not in cleaned
