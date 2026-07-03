---
name: "任务队列与 scheduler 多 worker 只读审计"
type: "task"
tags: [task-queue, scheduler, worker, multi-worker, audit, r2]
agent: "codex-flow-audit-tasks-r2"
created: "2026-07-03T09:35:19.748351+00:00"
---

# 结论

本次只读审计任务队列、定时任务、后台 worker、多 worker 状态流程；未改代码、未 commit。

# 关键证据

- 活栈为 `uvicorn app.main:app --workers 3`，端口 33000。
- `framework_system_task_queues` 当前 2446 行：completed 1539、failed 905、pending 1、cancelled 1、running 0。
- failed 全部超过 1 小时，主要为 `kb_pipeline` 769（File not found 710）和 `profile_evolve` 135（No module named init_db 130）。
- scheduler 共 150 行，其中 146 行 parameters 里 title/action_description 为空；145 个已 completed 且 result 为 success true/空动作，1 个未来 pending（id 1050，scheduled_at 2027-01-01 07:59 +08）。
- 当前 scheduler 创建路径在 2026-07-03 15:27 后已有 `_normalize_required_text`，能阻止新空 title/action；旧空数据来源在验证前历史版本。
- task worker claim 使用 `FOR UPDATE SKIP LOCKED`，当前 running=0/orphan=0，未发现当前重复消费证据。
- worker health 的 `_worker_task/_last_active/_HANDLERS` 是进程内状态；多 worker 下只能代表命中的进程，不是全局 worker 心跳。
- event bus 使用 DB lease + SKIP LOCKED，但 retry 时若当前进程没有匹配 handler，存在把旧 failed module_results 直接标 completed 的代码风险；当前 DB 未发现 completed 且 module_results success=false 的行。

# 问题队列

P0：未发现当前活跃 P0。没有 running orphan 或当前重复消费证据。

P1：scheduler 历史空 payload 会继续假成功；旧数据已产生 145 个空标题 completed success，未来 pending id 1050 到点仍会空动作完成。
P1：failed 历史债仍高水位，905 条全部为历史失败，治理能力存在但未应用到当前库。
P1：多 worker 健康/状态口径仍是进程内视角，不能证明所有 worker 的真实活跃状态。
P1：event bus retry 在 handler 缺失/未注册时可能误标 completed，需加 guard 与测试。
P2：`worker/audit` 的 historical_debt_total 被 500 limit 截断，真实 failed 是 905。
P2：`worker/status.oldest_waiting_seconds` 用 pending.created_at 计算，未来定时任务会被显示成等待 10 天以上，语义误导。
P2：`framework_system_tasks` 为空且仅模型引用，和真正队列表 `framework_system_task_queues` 命名容易混淆，建议文档/废弃口径收口。

# 可修复边界

- scheduler 数据和 handler 防线：`modules/scheduler/backend/router.py` + 只读 dry-run/一次性 DB 治理计划；当前模块任务可只碰 scheduler 模块，若要治理 framework 表需单独框架/数据治理任务。
- failed 历史债治理：`backend/app/services/task_debt_governance_service.py` 与 `/api/tasks/worker/governance`，先 dry-run 分类，再 apply allowlist。
- worker 全局状态：框架任务，涉及 `backend/app/services/task_worker.py`、`backend/app/routers/tasks.py`、`backend/app/main.py`，建议 DB/file-backed heartbeat。
- event bus guard：框架任务，涉及 `backend/app/services/event_bus.py` 与 `backend/tests/test_event_bus_retry.py`。
- audit/status 指标修正：框架任务，涉及 `backend/app/services/task_queue_audit_service.py`、`backend/app/routers/tasks.py`。

# 验证

使用工具台 brief、plan_task(task_type=investigation)、worktree_guard、db_reverse_audit(count_rows=true, table_filter=task)、db_schema、routes、capabilities、code_explore、code_node、tail_log、sql；并通过 curl 读取 `/api/health`、`/api/tasks/worker/audit`、`/api/tasks/worker/status`。未执行写入型治理或测试。
