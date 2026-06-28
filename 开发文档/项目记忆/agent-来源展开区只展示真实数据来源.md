---
name: "Agent 来源展开区只展示真实数据来源"
type: task
tags: ["agent", "references", "source-list", "skill-use", "citations"]
created: 2026-06-28
agent: zcode
---

# 改了什么
- 修复 Agent 来源展开区误显示工具名的问题。之前 `references_from_tool_events` 的 Generic fallback 会把任何 tool_result 都转成来源，导致 `web_search`、`skill_list`、`知识库` 这种工具名/泛称出现在来源列表。
- 删除工具名兜底：只有能提取到真实 URL、文件名/路径、知识库文档/页码时才生成 references。
- 增加 `skill_use` 解包：当工具结果由 `skill_use` 包装时，优先读取内层 `name/skill_name/tool_name` 和 `result/data/output`，再按 `web-tools__search`、`web-tools__fetch`、`knowledge__search` 等提取真实来源。
- 新增 `modules/agent/backend/test_references_from_tool_events.py`，覆盖 skill_use 内层 web 搜索 URL 提取，以及 `skill_list/web_search` 不应作为来源。

# 验证了什么
- `ruff check modules/agent/backend/_utils.py modules/agent/backend/test_references_from_tool_events.py`：All checks passed。
- `pytest modules/agent/backend/test_references_from_tool_events.py modules/agent/backend/test_model_client_inline_tool_calls.py`：4 passed。
- `cd frontend && npm run build`：通过。
- `probe GET /api/agent/health`：success true。

# 说明
- 用户看到正文里的 `<a href=...>来源</a>` 是 LLM 自己生成的 Markdown 链接锚文本，不是 footer 来源组件；可通过提示词要求 LLM 用页面标题/关键词作锚文本。footer 来源展开区现在不会再显示工具名。
