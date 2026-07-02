---
name: "memory-backfill-governance节点1-证据与边界确认"
type: "task"
tags: [memory, embedding-backfill, governance, 20260703]
agent: "memory-backfill-governance-worker"
created: "2026-07-02T16:22:24.064685+00:00"
---

节点1完成：已按 AGENTS 读取 开发文档/README.md，调用 brief/plan_task/worktree_guard。当前工作树存在并行 agent 改动，不能 revert；memory 模块内已有未提交改动：modules/memory/backend/services/embedding_service.py、modules/memory/sandbox/test_module.py。CodeGraph/工具台证据显示 memory 当前公开能力没有 embedding 历史回填/治理入口；embedding_service.py 仅有 _compute_embedding 与 _update_embedding_sql，影响面为 memory_service.py 与 capabilities.py。后续实现必须限制在 modules/memory/**，并保留 db-backtrace-r2 对 asyncpg/pgvector 参数化 CAST(:embedding AS vector(1024)) 的修复。
