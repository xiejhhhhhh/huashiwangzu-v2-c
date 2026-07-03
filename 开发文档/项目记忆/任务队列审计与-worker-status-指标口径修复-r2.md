---
name: "任务队列审计与 worker status 指标口径修复 r2"
type: "task"
tags: [task-queue, audit, status, metrics, r2]
agent: "codex-task-audit-metrics-r2"
created: "2026-07-03T09:48:22.409745+00:00"
---

# 改了什么

- `backend/app/services/task_queue_audit_service.py`：`historical_debt_total` 与 `classification.historical_failed_debt_count` 改为单独 `count()` 聚合，不再受历史失败样本上限 500 截断。
- `backend/app/routers/tasks.py`：`/api/tasks/worker/status` 的 `oldest_waiting_seconds` 只统计已经 due/past 的 pending 任务；未来 `scheduled_at` 的 pending 不再按老 `created_at` 计入等待时长。
- `backend/tests/test_task_queue_audit.py`：补 501 条历史失败任务的非截断回归测试，以及未来定时 pending 不污染 `oldest_waiting_seconds` 的回归测试。

# 验证了什么

- `ruff check backend/app/services/task_queue_audit_service.py backend/app/routers/tasks.py backend/tests/test_task_queue_audit.py` 通过。
- `pytest backend/tests/test_task_queue_audit.py`：12 passed。
- 重启后 probe `/api/tasks/worker/status`：当前仅未来定时 pending 时 `oldest_waiting_seconds=null`。
- probe `/api/tasks/worker/audit`：`historical_debt_total=905`，与当前 failed 总量对齐，不再是 500。
- probe `/api/health`：200，`status=ok`，worker running。
- `tail_log`：无新增错误输出。

# 残留风险

- 响应字段未变，仅修正聚合口径，兼容风险低。
- 当前工作区有其他 agent 的 `modules/**` 脏改和记忆文件，非本任务改动，未触碰；本任务未 commit/push。

# 关联 commit

- 未提交。
