---
name: "agent profile_evolve handler 注册路径清理 r3"
type: "task"
tags: [agent, profile_evolve, task_worker, handler_registration, verification, r3]
agent: "agent-profile-registration-cleanup-r3"
created: "2026-07-03T10:18:21.329225+00:00"
---

任务：清理 profile_evolve handler 重复注册路径，保持单一注册来源，避免启动覆盖/排障噪声。

改动：
- `modules/agent/backend/handlers/tasks.py` 删除 import-time `register_task_handler(...)` 副作用，改为只定义后台任务 handler。
- `modules/agent/backend/bootstrap.py` 成为 agent 后台任务唯一注册入口，继续注册 `profile_evolve`，并补齐 `agent_context_compact`，避免从 tasks.py 移除顶层注册后丢失该 handler。
- 新增 `modules/agent/backend/test_task_registration.py`，验证 reload `handlers.tasks` 不会偷偷注册 handler，且 `bootstrap.register_agent_tasks()` 会注册 `profile_evolve`、memory、slow tool、workflow、context compact 全套 handler。

验证：
- `ruff check` 通过：`modules/agent/backend/bootstrap.py`、`modules/agent/backend/handlers/tasks.py`、`modules/agent/backend/test_task_registration.py`。
- `pytest modules/agent/backend/test_task_registration.py`：1 passed。
- `pytest backend/tests/test_agent_profile_evolve_soft_failure.py`：3 passed。
- 合跑上述两个目标：4 passed。
- `/api/health` 200，worker.running=true，`registered_handlers` 包含 `profile_evolve`。

边界：本任务只改 agent 允许范围内文件，未触碰 backend/content、knowledge/upload、modules/knowledge 或其他代理文件；未 commit/push。当前共享工作树仍有其他代理留下的 backend/content、task audit、knowledge、运行态 dirty 项，worktree_guard/finish_task 整体红，需要按各自任务归属处理。
