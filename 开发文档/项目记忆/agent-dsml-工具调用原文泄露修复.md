---
name: "Agent DSML 工具调用原文泄露修复"
type: task
tags: ["agent", "dsml", "tool-calls", "leak-fix", "frontend", "backend"]
created: 2026-06-28
agent: zcode
---

# 改了什么
- 修复 Agent 回复中 DeepSeek DSML 工具调用原文泄露：`model_client._normalize_inline_markup` 现在识别 `<｜｜DSML｜｜...>`，并覆盖 `tool_calls` 复数容器。
- `parse_inline_tool_calls` 能把用户复现的 DSML `skill_use` 调用解析成标准 tool_calls，避免进入最终回复正文。
- `final_clean_content` 增强为最终落库兜底，剥离 `<tool_call>`/`<tool_calls>` 容器与残留 invoke。
- Agent 前端 `cleanXmlContent` 同步补 DSML 展示层兜底。
- 新增 `modules/agent/backend/test_model_client_inline_tool_calls.py` 回归测试。

# 验证了什么
- `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/backend/.venv/bin/pytest /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/agent/backend/test_model_client_inline_tool_calls.py`：2 passed。
- `ruff check modules/agent/backend/services/model_client.py modules/agent/backend/test_model_client_inline_tool_calls.py`：All checks passed。
- `cd frontend && npm run build`：通过。
- `probe GET /api/agent/health`：success true。

# 是否还有残留风险
- 收尾工具 `finish_task` 误把开工前已有的 `backend/data/agent/*.json` 运行态脏文件算作模块边界违规；本次产品相关改动经 `git -C ... status --short modules/agent` 确认为仅在 `modules/agent/` 内。
- 未提交 commit。
