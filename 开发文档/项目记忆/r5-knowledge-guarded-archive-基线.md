---
name: "R5 knowledge guarded archive 基线"
type: "task"
tags: [r5, knowledge, pipeline-debt, baseline]
agent: "codex-r5-knowledge-archive-b"
created: "2026-07-03T11:49:05.043262+00:00"
---

R5 第一阶段任务信 B 开工基线：工作区初始干净；只读 SQL 显示 framework_system_task_queues 中 knowledge/kb_pipeline 状态为 completed=957、failed=769。全量 failed 分类估算：source_file_missing=358、source_file_deleted=286、doc_deleted=81、doc_missing=24、file_row_live_or_other=13、async_context_error=4、parser_no_content_blocks=2、duplicate_or_stale_parse_lock=1。本泳道只实现并验证 guarded archive，实际可归档范围限定为 doc_missing/source_file_missing/source_file_deleted；doc_deleted、parser/greenlet/live retry/stale lock 不批量变更。
