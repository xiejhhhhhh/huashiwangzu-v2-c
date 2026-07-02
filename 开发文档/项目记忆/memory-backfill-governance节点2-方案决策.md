---
name: "memory-backfill-governance节点2-方案决策"
type: "architecture"
tags: [memory, embedding-backfill, governance, capability, 20260703]
agent: "memory-backfill-governance-worker"
created: "2026-07-02T16:23:17.083400+00:00"
---

节点2完成：决定在 memory 模块内实现安全治理链路，而不是直接 SQL 批量回填。方案：新增/扩展 modules/memory/backend/services/embedding_service.py，提供 backfill_missing_record_embeddings(db, owner_id=None, limit=20, dry_run=True, run_dream=False)，先统计 memory_records 总量/with_embedding/missing，并按 owner + limit 选出缺 embedding 记录；dry_run 只返回采样和诊断，不写库；非 dry_run 逐条调用既有 _compute_embedding 与 _update_embedding_sql，失败记录到 failures，继续处理；可选 run_dream 在本次成功回填后按 owner 触发 memory_service._do_dream 建链。入口通过 memory:backfill_embeddings admin-only capability 暴露，参数 dry_run/limit/owner_id/run_dream；manifest public_actions 与 sandbox 契约同步。
