---
name: "Agent thinking router verification"
type: task
tags: ["agent", "thinking-router", "verification", "bug"]
created: 2026-06-27
agent: zcode
---

本轮核验结论：思维等级路由器相关改动尚未完全落地。`modules/agent/backend/engine/thinking_router.py`、`engine.py`、`conversation_runtime.py` 当前存在 ruff/运行时错误：`engine.py` 在 `diagnosis` 未定义前写入思维路由结果，并引用了未导入的 `_apply_workflow_injection`；`conversation_runtime.py` 直接调用 `assemble_context` 但未导入。`thinking_router.py` 存在未使用导入。`run_init()` 已调用 `ensure_thinking_level_table()`，但活库中 `agent_thinking_levels` 表仍未出现。`/api/agent/health` 与 `/api/agent/conversations` probe 通过，说明主路由可用，但思维路由链路未通过静态与数据库核验。
