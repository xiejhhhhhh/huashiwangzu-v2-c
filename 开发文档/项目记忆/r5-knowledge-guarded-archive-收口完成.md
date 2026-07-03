---
name: "R5 knowledge guarded archive 收口完成"
type: "task"
tags: [r5, knowledge, pipeline-debt, archive, final]
agent: "codex-r5-knowledge-archive-b"
created: "2026-07-03T11:52:05.648895+00:00"
---

R5 第一阶段任务信 B 完成：在 modules/knowledge/backend/services/pipeline_debt_service.py 中将 archive_obsolete 的 archiveable 范围收窄为 doc_missing/source_file_missing/source_file_deleted，doc_deleted 改为 skipped；task_ids 精准 apply 时底层查询不再套 limit；archive result 保留 status=skipped、archived_by、classification、reason、document_id、file_id、previous_error_message、previous_status、previous_result；apply 返回新增 changed_by_category/skipped_by_category，dry_run 与非 dry_run shape 一致。测试补在 modules/knowledge/backend/tests/test_pipeline_debt_service.py，覆盖只归档三类、parser/greenlet/live retry/doc_deleted 不动、task_ids 精准小批、previous 信息保留、dry_run 不 commit。验证：ruff 两文件 passed；pytest test_pipeline_debt_service.py 11 passed；活栈只读 knowledge:classify_pipeline_debt 与 /api/knowledge/governance/pipeline-debt/dry-run 均 200。未做生产批量 mutation。只读候选样本：doc_missing task_ids 4567-4573 前五个，source_file_deleted 3026-3030，source_file_missing 3052-3056。当前 worktree 有并行 worker 的 dev_toolkit 与其他 knowledge 文件 dirty，不属于本泳道改动；本泳道实际代码改动仅 pipeline_debt_service.py 与 test_pipeline_debt_service.py。commit：未提交。
