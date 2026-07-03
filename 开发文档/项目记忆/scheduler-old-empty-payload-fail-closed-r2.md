---
name: "scheduler old empty payload fail closed r2"
type: "task"
tags: [scheduler, task-queue, audit-r2, fail-closed, sandbox-test]
agent: "codex-scheduler-old-payload-guard-r2"
created: "2026-07-03T09:42:46.416789+00:00"
---

# 改了什么
- 修复 `modules/scheduler/backend/router.py` 的 `_cap_scheduled_job_handler`：旧任务参数缺失或空白 `title` / `action_description` 时不再按空动作完成，而是返回 `success:false`、`status:"failed"`、`error`、`executed:false`。
- 同步把缺 `creator_id` 的返回形状收口为 failed，便于 task worker 标记失败而不是假成功。
- 补充 `modules/scheduler/sandbox/test_module.py`：覆盖旧空 payload、缺 creator_id、正常最小 payload，并 patch `module_registry.call_capability` 避免真实 Agent/IM/DB 副作用。

# 验证了什么
- `ruff check modules/scheduler/backend/router.py modules/scheduler/sandbox/test_module.py` 通过。
- `pytest modules/scheduler/sandbox/test_module.py`：20 passed。
- `/api/health` 返回 success true，`scheduled_agent_job` handler 已注册。
- `scheduler:list` capability 返回 success true；backend tail_log 为空。

# 残留风险
- 本次代码 diff 只在 `modules/scheduler/**`。
- 收尾时工作区存在非本任务的 `backend/app`、`modules/agent`、`modules/browser-tools` 修改及此前未跟踪项目记忆文件；未触碰、未回退、未提交。

# 关联 commit
- 未 commit/push（按任务要求）。
