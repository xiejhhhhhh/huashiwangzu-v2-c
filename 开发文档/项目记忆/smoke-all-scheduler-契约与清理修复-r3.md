---
name: "smoke_all scheduler 契约与清理修复 r3"
type: "task"
tags: [dev-toolkit, smoke_all, scheduler, cleanup, r3]
agent: "codex-main-conductor-r3"
created: "2026-07-03T10:54:19.617100+00:00"
---

主会话从 smoke_all 失败倒推发现 dev_toolkit/smoke.py 仍按旧 scheduler:create payload(name/cron/action) 调用，当前 scheduler 契约已要求 title/action_description/scheduled_at/recur。修复为创建未来一次性 scheduler 任务，随后 cancel，并通过 DB 精确删除本轮 smoke 标题的 framework_system_task_queues 记录，避免回归测试自己留下 pending/历史记录。验证：ruff dev_toolkit/smoke.py 通过；smoke_all(skip_ui=true) 从 E8 FAIL 变为 PASS_WITH_DEBT，E8 输出 task_id=8890, cleaned=1，failed 基线 905 -> 905 无新增，pending 回到基线 1。此前误创建的 smoke-1783075644446 已手工删除 1 条。
