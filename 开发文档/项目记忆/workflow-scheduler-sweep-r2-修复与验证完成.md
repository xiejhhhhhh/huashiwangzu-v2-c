---
name: "workflow/scheduler sweep r2 修复与验证完成"
type: "task"
tags: [scheduler, workflow, module-sweep, r2, validation, task_id:workflow-scheduler-sweep-20260703-r2]
agent: "codex-workflow-sweep-20260703-r2"
created: "2026-07-03T07:14:11.315278+00:00"
---

目标目录：modules/workflow 与 workflow-* 不存在，本轮按任务说明选择最接近流程/执行/状态/队列语义的 modules/scheduler。

问题清单：1) HTTP create 与 capability create 校验重复且不一致，capability 可创建空 title/action 或非法 recur；2) recur 只判断 cron: 前缀，cron:xx:yy/cron:24:00 会进入任务队列，完成重排时可能让 task_worker 抛错并留下 running/stale 债；3) cancel 允许 running/cancelled 等非 pending 状态，存在取消后又被 worker finish 覆盖的竞态；4) list 对 parameters 反复 json.loads，历史坏 JSON 可拖垮整个列表；5) runtime scheduler BASE=/api/scheduler 会和 getApiUrl('/api') 叠成 /api/api/scheduler；6) manifest public_actions 的 create 缺 title 契约；7) sandbox 仍使用旧 cron 风格和 task_id 输出字段，覆盖不到真实漂移。

修复：modules/scheduler/backend/router.py 新增统一校验/建表 helper，HTTP 和 capability 共用；scheduled_at 统一转 UTC；recur 限定 hourly/daily/weekly/cron:HH:MM 并做范围校验；cancel 仅允许 pending；list 使用容错参数解析；capability 对业务校验返回 success:false。modules/scheduler/runtime/index.ts 修正 BASE=/scheduler。manifest 补 title 和 recur 描述。sandbox 增加 title/recur/runtime path/cancel 输出覆盖并对齐 cron:HH:MM。

验证：ruff router+sandbox 通过；py_compile 通过；pytest modules/scheduler/sandbox/test_module.py 14 passed；python3.14 modules/scheduler/sandbox/test_module.py PASS；run_test backend/tests/test_agent_scheduler_task_semantics.py 9 passed；进程内 helper 语义验证 invalid recur/空 title PASS；活系统 /api/health ok，scheduler:create/list/cancel 走通，测试任务 5242 已从 framework_system_task_queues 精确删除；backend tail_log 空。finish_task 因其他并行 worker 脏文件返回 success:false，但 forbidden_hits=0，本 worker 代码改动只在 modules/scheduler。
