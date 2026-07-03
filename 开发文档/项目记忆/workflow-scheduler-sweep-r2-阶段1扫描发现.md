---
name: "workflow/scheduler sweep r2 阶段1扫描发现"
type: "task"
tags: [scheduler, workflow, module-sweep, r2, heartbeat, task_id:workflow-scheduler-sweep-20260703-r2]
agent: "codex-workflow-sweep-20260703-r2"
created: "2026-07-03T07:05:15.101596+00:00"
---

阶段1：仓库没有 modules/workflow 或 workflow-* 模块，按任务要求选择最接近流程/执行/状态/队列语义的 modules/scheduler。已读开发文档入口、框架/底层/模块 README、modules/scheduler/README.md；已跑 brief/plan_task/worktree_guard/code_explore/code_node/code_impact/routes/capabilities/db_schema。当前工作区有其他 worker 在 codemap/image-gen/knowledge/office-gen/terminal-tools 等目录的脏改动，本 worker 不触碰。候选问题：scheduler HTTP 与 capability 创建逻辑重复且校验不一致；cron 只校验前缀；capability handler 返回 success:false 可能被外层 /api/modules/call 包成 HTTP 200 data；manifest public_actions 缺 title required 声明；sandbox 仅覆盖浅契约，需要补输入校验/假成功/取消边界。
