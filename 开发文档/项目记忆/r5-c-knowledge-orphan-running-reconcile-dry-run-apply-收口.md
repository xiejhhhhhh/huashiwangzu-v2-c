---
name: "R5 C knowledge orphan running reconcile dry-run/apply 收口"
type: "task"
tags: [r5, knowledge, pipeline, reconcile, orphan-running]
agent: "codex-r5-knowledge-reconcile-c"
created: "2026-07-03T11:54:53.576419+00:00"
---

# 改了什么
- 新增 `modules/knowledge/backend/services/pipeline_reconcile_service.py`，为 `kb_pipeline_runs.status='running' AND task_id IS NULL` 提供独立 dry-run/apply reconcile。
- 分类归一为 `source_file_missing`、`source_file_deleted`、`doc_missing`、`doc_deleted`、`live_without_task`；只有 missing/deleted 生命周期类可 apply。
- apply 终态使用 `skipped`，对齐 pipeline orchestrator 的 source unavailable 语义；写入 `completed_at`、`reason`，并在 `diagnostics_json` 保留原始诊断及 `previous_status`。
- router 增加 `/api/knowledge/governance/pipeline-runs/orphan-running/dry-run` 与 `/apply`，并注册 `knowledge:reconcile_orphan_pipeline_runs` admin capability；manifest public_actions 同步声明。

# 验证了什么
- `backend/.venv/bin/ruff check modules/knowledge/backend` 通过。
- `modules/knowledge/backend/tests/test_pipeline_reconcile_service.py` 4 passed，覆盖 dry-run、apply source_missing、拒绝 live_without_task、保留 previous diagnostics、task_id not null 不处理。
- `modules/knowledge/backend/tests/test_pipeline_debt_service.py` 11 passed；两文件合跑 15 passed。
- 活栈只读 `GET /api/knowledge/governance/pipeline-debt/dry-run?limit=500` 仍显示 orphan running summary: `orphan_run_source_file_missing=3`、`orphan_run_source_file_deleted=1`。

# 是否还有残留风险
- 未执行生产 apply，没有生产数据 mutation。
- 工作区有其他并行 worker 的 `dev_toolkit/*` 和 knowledge 泳道改动，finish_task 边界检查因此失败；本轮未回退或修改这些文件。
- `router.py` 原已超过 1000 行，本轮只做窄接线，未开展 router 拆分。
