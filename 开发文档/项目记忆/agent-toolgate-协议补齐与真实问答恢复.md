---
name: "Agent ToolGate 协议补齐与真实问答恢复"
type: task
tags: ["agent", "toolgate", "deepseek", "tool-calls", "sse", "final-summary"]
created: 2026-06-28
agent: zcode
---

# 改了什么

继续排查用户 04:25 的 Agent 失败，确认不是云端 DeepSeek 不可用，而是运行时工具协议链路还有两处问题：

1. ToolGate 拒绝未暴露工具名时没有补对应 `tool` 消息，导致下一轮触发 OpenAI/DeepSeek 协议预检错误：`assistant tool_calls missing matching tool results`。
   - 已在 `ToolLoopRuntime` 的 ToolGate 分支中，为每个被拒绝的 tool_call 追加 `tool_result` 事件、`role=tool` 消息和 pending event，再追加 retry user message。

2. 模型自然会调用已注册能力名 `knowledge__search` / `web-tools__search`，而当前 `build_tools()` 只暴露 `skill_list/skill_describe/skill_use`，ToolGate 只看暴露工具导致误拒。
   - 已在 `ToolGate` 中加载当前角色可用的注册能力名（module__action），允许已注册能力直连通过；仍拒绝未注册名称。

3. final summary 阶段若模型又输出 DSML/tool_calls 文本，旧逻辑边流式吐出再清洗，最终变成空回复。
   - 已改为 final summary 先缓冲，提示“不要再调用工具，只输出最终答案”。
   - 清洗后若只剩 inline tool_calls，则用已返回的工具结果生成兜底答案，避免空回复。

# 验证

- 单测：`test_tool_gate.py` 新增“已注册但未暴露工具名可通过”和“未注册工具仍拒绝”。
- `pytest ../modules/agent/backend/test_tool_gate.py backend/tests/test_gateway_protocol.py backend/tests/test_gateway_retry.py ../modules/agent/backend/engine/test_event_store.py ../modules/agent/backend/test_content_gate.py`：41 passed。
- `ruff check` 覆盖改动文件：通过。
- 后端重启成功。
- 真实 live Agent SSE 验证新对话 conv=82，输入“抖音投流，巨量后台，是哪一个页面，可以看到对标视频的？”：
  - status 200
  - 无 error event
  - 产生最终答案，包含“巨量云图 → 话题分析”和“巨量创意 → 创意灵感”入口
  - event tail 包含 token/work_done/round_usage/references
- `/api/agent/health` 200；`/api/gateway/health` 200，opencode=true。

# 残留风险

模型可能仍会在复杂场景中选择次优工具，但不会再因已注册工具名直连、ToolGate 拒绝或 final summary DSML 导致协议错误/空回复。工作区仍有此前既有数据和文档改动未处理。
