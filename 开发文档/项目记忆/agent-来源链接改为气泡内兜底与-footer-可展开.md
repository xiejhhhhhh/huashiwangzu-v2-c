---
name: "Agent 来源链接改为气泡内兜底与 footer 可展开"
type: task
tags: ["agent", "references", "citations", "message-bubble", "source-links"]
created: 2026-06-28
agent: zcode
---

# 改了什么
- 按用户反馈调整 Agent 来源展示：保留 footer 来源入口，但改为 `来源 N` 可收缩/展开按钮，不再常驻占用气泡下方空间。
- `MessageBubble.vue` 在助手回复气泡正文内追加小字号来源兜底：当模型正文没有 Markdown 链接时，自动在气泡内容末尾追加 `来源：链接1 · 链接2`；若模型已生成链接，则不重复追加。
- footer 展开后显示完整来源列表，点击外链仍通过 `window.open` 绕过桌面壳拦截。
- `context_pipeline.py` 引用提示词改为要求 LLM 优先把页面名/平台功能名/关键结论词写成 Markdown 链接，而不是只在句末泛泛标注。

# 判断
- “关键词加超链接”应主要由 LLM 根据语义生成，因为规则无法可靠判断哪段正文对应哪个来源；规则层只做兜底：没检测到正文链接时，把 references 元数据以小字号来源链接补进气泡内。

# 验证了什么
- `ruff check modules/agent/backend/engine/context_pipeline.py modules/agent/backend/runtime/tool_loop_runtime.py modules/agent/backend/services/model_client.py modules/agent/backend/test_model_client_inline_tool_calls.py`：All checks passed。
- `pytest modules/agent/backend/test_model_client_inline_tool_calls.py`：2 passed。
- `cd frontend && npm run build`：通过。
- `probe GET /api/agent/health`：success true。
- `git status --short modules/agent`：相关改动均在 `modules/agent/`。

# 残留风险
- 如果 LLM 不按提示生成正文关键词链接，规则兜底会在气泡正文末尾追加来源链接，但不会强行给任意关键词自动套链，避免错链。
