---
name: "capability-contract-consistency-r4节点1-memory与desktop契约对齐"
type: "task"
tags: [capability-contract, manifest, register-capability, memory, desktop-tools, 20260703]
agent: "capability-contract-consistency-r4"
created: "2026-07-02T16:51:13.155581+00:00"
---

任务：审计 manifest public_actions 与后端 register_capability/实际 handler 契约是否漂移，重点 memory、desktop-tools，低成本扫描其它模块。

结论与改动：
- memory：manifest public_actions 补齐当前注册/handler 使用的公开参数：save.source、recall.limit、recall.expand_chain、rethink.tags、match_experience.team_owner_ids、experience_feedback.team_owner_ids；保留 backfill_embeddings admin-only 声明。
- desktop-tools：删除 router.py 中 list_files/search_files/read_file/list_apps 的重复 register_capability 注册块；删除 replace_file 注册里未实现的 conflict_policy 参数声明和注释，避免公开一个无效开关。
- backend/tests/test_module_boundary_contracts.py：新增 AST+manifest 静态契约检查，限定 memory、desktop-tools，检查 action 集合、min_role、参数名集合，以及重复注册。
- modules/memory/sandbox/test_module.py：同步参数样例，覆盖 source、limit、expand_chain、tags、team_owner_ids。
- 活系统：调用 /api/app-manager/apps/scan-register，同步 framework_app_registry 中 manifest 快照，updated=36；复验 desktop-tools:list_apps 返回 memory 新 public_actions。

验证：
- MCP run_test: backend/tests/test_module_boundary_contracts.py + backend/tests/test_module_capability_drift.py => 11 passed。
- pytest: modules/memory/sandbox/test_module.py => 24 passed。
- ruff: backend/tests/test_module_boundary_contracts.py、modules/desktop-tools/backend/router.py、modules/memory/sandbox/test_module.py 全绿。
- JSON manifest 校验通过。
- /api/health 200；memory:backfill_embeddings dry_run admin 调用 200；desktop-tools:list_apps viewer 调用 200。

注意：全局 worktree 仍有其它 agent 并行改动，worktree_guard 有 outside_allowed 但无 forbidden 命中。本节点不回退他人改动。
