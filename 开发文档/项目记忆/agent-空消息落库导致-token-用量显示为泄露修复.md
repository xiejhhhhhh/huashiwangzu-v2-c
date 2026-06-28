---
name: "Agent 空消息落库导致 token 用量显示为泄露修复"
type: task
tags: ["agent", "runtime", "empty-message", "token-leak", "retry"]
created: 2026-06-28
agent: zcode
---

本轮修复了“重试后空消息显示 token 用量标签构成的假泄露”问题。根本原因：retry 契约清空了 `full` 缓冲区后，最终轮模型未能产生有效正文，但空消息仍被 `persist_assistant` 落库（`final_clean_content` 清洗后才空，入口未防），meta 中的 timeline 和 usage 数据被前端渲染为 `WorkTraceGroup`（含“已工作 30秒”）和 `MessageBubble` token 标签（`92,264/613/92,877`），用户误认为泄露。

两处改法：
- backend `task_sink.py persist_assistant`：`final_clean_content` 后检查空字符串，返回 None 不落库，记 warning。
- frontend `index.vue expandTimeline`：工作组后面无有效 assistant 消息时，补占位文本 `（模型未能生成回复）`，且清零 usage 不让 token 标签显示。

验证：`ruff check` 全绿，`pytest test_stream_emitter_guardrails.py` 3 passed。提交 `d03fbbf`，后端已重启。边界：仅改 `modules/agent/backend/runtime/task_sink.py` + `modules/agent/frontend/index.vue`。
