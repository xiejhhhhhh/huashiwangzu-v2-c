---
name: "Agent fallback/tool_calls recovery hardening"
type: task
tags: ["agent", "fallback", "tool-calls", "stuck-detector", "gateway", "mcp"]
created: 2026-06-27
agent: zcode
---

修复 Agent 回退/tool_calls 恢复链路漏洞：recover_tool_calls 改为复用 gateway_router.chat 的 adapter 标准返回，消除直接 provider.chat raw 解析漂移；DeepSeekAdapter 的 ollama 分支补 tool_calls 提取；ToolLoopRuntime stuck detector 改为同一模型轮次只计一次，避免同轮多个相同 tool_calls 误触发；最终 assistant_msg event payload 使用 final_clean_content 清理；parse/final_clean 支持全角 ｜invoke 标记。补充回归测试：gateway adapters、inline/recover、tool_loop_runtime、stuck_detector。验证：MCP lint 相关 6 文件全通过；MCP run_test `tests/test_gateway_adapters.py tests/test_agent_inline_tool_calls.py tests/test_agent_tool_loop_runtime.py ../modules/agent/backend/engine/test_stuck_detector.py` 54 passed。注意：MCP run_test 当前以 backend/ 为 cwd，传 `backend/tests/...` 会找不到文件，可后续优化路径兼容。
