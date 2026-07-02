---
name: "memory-backfill-review-r3节点1-回填治理评审补完与验收"
type: "task"
tags: [memory, embedding-backfill, governance, review-r3, 20260703]
agent: "memory-backfill-review-r3"
created: "2026-07-02T16:42:57.102282+00:00"
---

memory-backfill-review-r3 接手 Halley/Maxwell 中断后的 memory embedding SQL/backfill governance 改动，只处理 modules/memory/**。结论：manifest/router/capability 的 memory:backfill_embeddings admin-only 链路已对齐；服务层 backfill_missing_record_embeddings 支持 dry_run 默认 true、limit 1-100、owner_id/owner 过滤、逐条计算 embedding 并用 CAST(:embedding AS vector(1024)) 参数化写入。补修：run_dream 后续建链改为降级路径，dream 异常时 rollback 当前 dream 事务、记录 dream_failures，并返回 diagnostic=completed_with_dream_failures，不抹掉已成功的 embedding updated 结果；sandbox 增加 dream 降级输出契约；顺手修复 modules/memory/backend/services/distill_service.py 的 ruff 导入/变量名问题以让 memory backend ruff 全绿。验证：backend/.venv/bin/ruff check modules/memory/backend modules/memory/sandbox/test_module.py 通过；modules/memory/sandbox/test_module.py 24 passed；backend/tests/test_engine_batch2.py 33 passed；backend/tests/test_memory_experience_scope.py 6 passed；活系统重启后 memory:backfill_embeddings dry_run admin 返回 total=37, with_embedding=4, missing=33, selected_count=1, processed=0, updated=0, diagnostic=dry_run_only；viewer 调用 403；limit=101 返回 422；owner_id=4 dry_run 返回 selected_count=5；SQL 统计仍为 37/4/33，证明 dry-run 未写库。风险：全局 worktree 仍有大量其他 agent 改动，worktree_guard/finish_task 因 outside-memory 既有改动失败；本 agent 的实际修改范围为 modules/memory/backend/router.py、services/capabilities.py、services/embedding_service.py、services/distill_service.py、manifest.json、sandbox/test_module.py。关联 commit：未提交。
