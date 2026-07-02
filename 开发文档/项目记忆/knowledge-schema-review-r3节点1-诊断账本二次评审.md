---
name: "knowledge-schema-review-r3节点1-诊断账本二次评审"
type: "task"
tags: [knowledge, review, pipeline-diagnostics, 20260703]
agent: "knowledge-schema-review-r3"
created: "2026-07-02T16:41:01.308829+00:00"
---

二次评审 Ramanujan 的 knowledge schema/diagnostics 改动。结论：`kb_pipeline_runs`/`kb_pipeline_stage_runs` 作为诊断账本，模型与 init_db 建表/索引/迁移一致；orchestrator 的 `_start_pipeline_run`、`_record_stage_run`、`_finish_pipeline_run` 使用独立 `AsyncSessionLocal`，异常只 rollback 诊断会话并 warning，不让诊断失败中断主 pipeline。raw/fusion 的诊断字段是产物元数据，不替代主状态；pipeline_service 仍只是转发到 orchestrator，router 只 enqueue `kb_pipeline`，未发现重复主流程。
