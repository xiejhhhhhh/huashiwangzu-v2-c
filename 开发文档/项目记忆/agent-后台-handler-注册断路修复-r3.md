---
name: "Agent 后台 handler 注册断路修复 r3"
type: "task"
tags: [agent, task-worker, handler-registration, r3, worker-registry]
agent: "codex-agent-bootstrap-handler-registration-r3"
created: "2026-07-03T11:02:43.686070+00:00"
---

## 我是谁
codex-agent-bootstrap-handler-registration-r3

## 做了什么
修复 Agent 模块 router 加载时没有注册 RuntimeTaskSink 后台任务 handler 的断路。`modules/agent/backend/router.py` 不再依赖过时的 `from .handlers import tasks` import side effect，而是在模块 router 被 manifest loader import 时显式调用 `register_agent_tasks()`，使 `profile_evolve`、`memory_distill`、`workflow_mine`、`agent_context_compact`、`memory_dream`、`agent_execute_slow_tool` 在每个后端 worker 进程的 task registry 中可见。

同时把 `ConversationRuntime` 从 router 顶层导入改为 `/chat` 与 `edit-resubmit` 端点内懒加载，降低模块加载阶段对 engine 子系统的耦合，避免测试环境中 engine import 污染影响 router import。新增 `modules/agent/backend/test_task_registration.py` 回归测试，覆盖 manifest loader 等价的 router import/reload 后 handler 必须进入 `task_worker._HANDLERS`。

## 边界说明
本轮产品代码改动只在 `modules/agent/backend/router.py` 与 `modules/agent/backend/test_task_registration.py`。没有修改 framework loader，也没有改 `backend/app`。证据表明框架 loader 已按 manifest 正确 import agent router，断点在 agent router 仍保留旧的 import-side-effect 注册写法，而 `handlers/tasks.py` 当前只定义 handler、不自注册；因此这是 agent 模块内修复，不是框架任务。

收尾时工作区出现 backend/codemap/douyin-delivery/knowledge/dev_toolkit 等并行未提交改动；开工 `worktree_guard` 为 clean，这些不是本任务改动，未回退。

## 验证
- ruff: `modules/agent/backend/router.py`、`modules/agent/backend/test_task_registration.py` all passed
- `modules/agent/backend/test_task_registration.py`: 2 passed
- `modules/agent/backend/test_async_compaction.py`: 16 passed
- `modules/agent/sandbox/test_module.py`: 6 passed
- `modules/agent/backend`: 242 passed
- 重启活栈后 `/api/health` worker.registered_handlers 包含 `profile_evolve`、`memory_distill`、`workflow_mine`、`agent_context_compact`
- 通过 `/api/tasks/submit` 投递 `workflow_mine` 验证任务 #8891，worker 将其从 pending 消费到 completed；随后已删除该测试任务清理数据
- `tail_log` 无新增错误输出

## 关联 commit
未提交，用户要求不要 commit/push。
