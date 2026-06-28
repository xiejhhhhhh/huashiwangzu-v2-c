---
name: "Agent 模型连接失败错误脱敏与工作组收尾修复"
type: task
tags: ["agent", "error-handling", "model-gateway", "sse", "frontend"]
created: 2026-06-28
agent: zcode
---

# 改了什么

修复 Agent/AI 助手在模型连接失败时把内部错误原文暴露给用户的问题。

- 后端 `content_gate.py` 新增 `user_safe_error_message()`，把 `Model error: All connection attempts failed`、`stream error`、timeout/provider/upstream 等底层错误统一转成用户提示：`模型服务暂时连接失败，请稍后重试。`
- `stream_emitter.py` 在上游流式 `error` 事件和异常 catch 中使用安全文案，同时日志保留原始错误。
- `tool_loop_runtime.py` 在模型降级链返回 error 或运行时异常时使用安全文案，同时记录真实错误。
- `frontend/index.vue` 收到 SSE error 时二次兜底清洗，并调用工作组收尾，避免“正在工作”一直挂着。
- `test_content_gate.py` 补充模型连接错误脱敏与业务短错误保留测试。

# 验证了什么

- `ruff check modules/agent/backend/runtime/content_gate.py modules/agent/backend/runtime/stream_emitter.py modules/agent/backend/runtime/tool_loop_runtime.py modules/agent/backend/test_content_gate.py`：通过。
- `pytest ../modules/agent/backend/test_content_gate.py`：16 passed。
- `GET /api/agent/health`：200 success。
- `frontend npm run build`：通过。

# 残留风险

本次只处理 Agent 模块内的用户可见错误脱敏和前端收尾。工作区开始前已有 `backend/data/agent/*`、`dev_toolkit/memory_embeddings.json`、开发文档索引等非本任务改动，未处理；`finish_task` 因这些既有非 `modules/agent/` 变更报告边界失败，但本次实际代码改动集中在 `modules/agent/`。
