---
name: "Agent 工具意图运行时契约重试"
type: task
tags: ["agent", "tool-contract", "runtime", "retry", "guardrail"]
created: 2026-06-28
agent: zcode
---

本轮把 Agent 的“承诺查/搜/用工具但没有产生 tool call”从前端/流式报错兜底升级为运行时契约：StreamEmitter 检测到不合规最终文本时撤回已流出的 token，并返回 `_retry_tool_intent_contract` 控制信号；ToolLoopRuntime 捕获该信号后向本轮 messages 注入硬约束反馈，要求模型要么发出真实工具调用、要么直接回答，不再把“我去查一下”持久化为最终回复。连续不合规才报错终止，避免无限循环。补充 `test_stream_emitter_guardrails.py`，改为隔离加载目标文件，避免 runtime 包初始化副作用。验证：`backend/.venv/bin/pytest modules/agent/backend/test_stream_emitter_guardrails.py` 3 passed；`backend/.venv/bin/ruff check modules/agent/backend/runtime/stream_emitter.py modules/agent/backend/runtime/tool_loop_runtime.py modules/agent/backend/test_stream_emitter_guardrails.py` All checks passed。未提交 commit。
