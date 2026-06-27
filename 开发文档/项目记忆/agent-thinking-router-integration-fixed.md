---
name: "Agent thinking router integration fixed"
type: task
tags: ["agent", "thinking-router", "fix", "verification"]
created: 2026-06-27
agent: zcode
---

修复 Agent thinking router 集成问题：1) `init_db.py` 将误嵌的 agent_events 建表块拆为 `ensure_event_table()`，`run_init()` 可幂等创建 `agent_thinking_levels` 与 `agent_events`；2) `engine.py` 修复 `diagnosis` 未定义，导入并复用 `workflow_strategy.apply_workflow_injection`，将 thinking 路由诊断合并到预算诊断；3) `conversation_runtime.py` 补 `assemble_context` 导入，并把正常流程 `record_thinking_feedback()` 移出 understanding 条件块；4) `thinking_router.py` 清理未使用导入；5) `ToolLoopRuntime` 与 `StreamEmitter` 增加 `suppress_thinking`，当路由等级为 `none` 时不再向前端输出 thinking 流。验证：相关 6 个 Python 文件 ruff 全绿；重启后 `/api/health` 200 且 `module_errors:null`；SQL 确认 `agent_thinking_levels`/`agent_events` 存在；真实请求 `你好` 落库为 `none/rule/confidence=1/accepted=true`，`帮我分析一下` 落库为 `high/rule/confidence=0.9/accepted=true`。MCP `run_test` 仍报工具自身 `name '_run_test' is not defined`，未能用该工具跑单测。
