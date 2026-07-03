---
name: "p0-task-queue-health-worker-debt-signal-framework-fix-r3"
type: "task"
tags: [p0, task-queue, health, worker, framework]
agent: "codex-framework-task-queue-knowledge-debt-audit-r3"
created: "2026-07-03T11:14:46.783473+00:00"
---

# 稳定节点：框架 task_queue health/worker 债务信号修复

## 本域问题队列
- P0 health false-green/债务信号弱：`/api/health` 历史 `failed=905`、completed 语义失败总量 `217` 需要显式暴露，不能只靠 `/api/tasks/worker/audit` 才能看到。
- P0 worker 多进程恢复：并发启动恢复 stale `running` 时，同一任务可能被多个恢复协程重复加 `retry_count`，触顶后误变 `failed`。
- P1 worker 健康口径：`worker_health().last_active` 是进程内内存，uvicorn `--workers 3` 下不是全局 worker 活跃时间。
- P1/P2 knowledge 诊断流水：`kb_pipeline_runs` orphan `running`、knowledge classifier 覆盖缺口仍在，但 `modules/knowledge/backend/services/pipeline_debt_service.py` 当前为他人脏改，未在本节点触碰。

## 已修复
- `/api/health.task_queue` 增加 `historical_failed_debt`、`semantic_failed_completed_total`、`debt_status`；当前磁盘口径是历史债务不拉低 live `status`，但 `debt_status=debt` 明确暴露治理债。
- `/api/health` 继续对 24h completed 语义失败降级，新增总量字段用于 dashboard/governance 使用。
- `task_worker._recover_stale_tasks` 改为带 `id/status/started_at` 条件的原子更新，避免并发恢复重复回收同一 running 行。
- `worker_health()` 增加 `process_local=true`、`pid`、`last_active_scope=process`，明确多 worker 下 last_active 不是全局状态。

## 验证
- `cd backend && .venv/bin/python -m ruff check app/main.py app/services/task_worker.py tests/test_framework_health.py tests/test_task_worker_recovery.py`：通过。
- `cd backend && .venv/bin/python -m pytest tests/test_framework_health.py tests/test_task_worker_recovery.py tests/test_task_queue_audit.py`：26 passed, 1 warning。
- `curl /api/health` 曾在热加载窗口返回 `status=degraded` 且显示 `failed=905`、`historical_failed_debt=905`、`semantic_failed_completed_total=217`、worker `process_local=true`；当前磁盘测试锁定历史债务不降级 live status，仅 `debt_status=debt`。

## 残留风险 / 后续拆分
- 是否让历史债务拉低 `/api/health.status` 仍需框架治理口径确认；当前实现避免常驻红灯，但 dashboard/release gate 必须消费 `task_queue.debt_status` 才不 false-green。
- health 的 completed 语义失败总量是基于文本匹配的轻量健康信号；治理详情仍以 `/api/tasks/worker/audit` 和 governance dry-run 为准。
- 跨 worker 全局心跳尚未持久化，建议独立任务落 DB/文件心跳。
- knowledge `kb_pipeline_runs` orphan running 与 classifier drift 留给 knowledge worker；本节点未触碰 dirty knowledge 文件。
