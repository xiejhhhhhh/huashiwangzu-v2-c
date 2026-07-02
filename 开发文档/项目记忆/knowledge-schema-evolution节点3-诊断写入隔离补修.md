---
name: "knowledge-schema-evolution节点3-诊断写入隔离补修"
type: "gotcha"
tags: [knowledge, pipeline-diagnostics, best-effort, rollback, 20260703]
agent: "knowledge-schema-evolution-worker"
created: "2026-07-02T16:24:30.149634+00:00"
---

主线程评审指出 pipeline diagnostics helper 虽标注 best-effort，但同一 SQLAlchemy session 中 flush 失败若不 rollback，会让主 pipeline session 进入 failed transaction。已补修：`_start_pipeline_run`、`_finish_pipeline_run`、`_record_stage_run` 改为独立 `AsyncSessionLocal()` 诊断会话，异常时对诊断会话 rollback，避免污染主链路；新增测试覆盖诊断 flush/commit 失败时 pipeline 仍返回 done、主 db 不 rollback、诊断 db 有 rollback。
