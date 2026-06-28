---
name: "Agent 回复来源小字号链接展示修复"
type: task
tags: ["agent", "references", "source-links", "frontend", "sse"]
created: 2026-06-28
agent: zcode
---

# 改了什么
- 修复 Agent 回复来源链接缺失：`MessageBubble.vue` 现在读取 `message.references`，在助手气泡下方以小字号 `来源：链接1 · 链接2` 形式展示，不使用卡片/侧栏组件。
- 来源链接去重并最多展示 6 条；有 URL 的以 `<a>` 打开外部链接，无 URL 的本地/知识库来源以文本展示。
- `tool_loop_runtime.py` 在最终持久化后通过 `references_from_tool_events(tool_events)` 计算本轮来源，并发出 `references` SSE 事件。
- `index.vue` 接收 `references` SSE 并挂到最近一条 assistant 消息，避免实时流期间必须刷新才显示来源。

# 验证了什么
- `ruff check modules/agent/backend/runtime/tool_loop_runtime.py modules/agent/backend/services/model_client.py modules/agent/backend/test_model_client_inline_tool_calls.py`：All checks passed。
- `pytest modules/agent/backend/test_model_client_inline_tool_calls.py`：2 passed。
- `cd frontend && npm run build`：通过。
- `probe GET /api/agent/health`：success true。
- `git status --short modules/agent`：相关改动均在 `modules/agent/`。

# 残留风险
- 仍保留模型正文内 Markdown 链接能力；本次新增的是元数据兜底展示，二者可能同时出现，但元数据展示更稳定。
- 工作区仍有先前运行态脏文件和项目记忆索引变动，未处理。
