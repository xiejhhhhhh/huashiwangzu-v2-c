---
name: "knowledge 文件生命周期修复 r3"
type: "task"
tags: [knowledge, file-lifecycle, pipeline, source-unavailable, r3]
agent: "knowledge-file-lifecycle-fix-r3"
created: "2026-07-03T10:17:19.788939+00:00"
---

Agent: knowledge-file-lifecycle-fix-r3

完成 knowledge 文件生命周期修复：
- `list_documents` 只列出源文件仍存在且未删除的文档，并在 payload 中暴露 `source_available/source_state`。
- `get_document` 对 missing/deleted source 先标记 `parse_error=source_file_missing/source_file_deleted`，再抛 NotFound，避免 API 把历史文档当正常详情返回。
- `_run_pipeline` 在任何 parse/index 前先校验 source live；missing/deleted 时直接返回 `status=skipped`、`classification=source_unavailable`，并保持 chunks/raw/fusion 等派生产物不被本轮误写或清空。
- 前端 knowledge 类型补齐 `source_available/source_state`。
- 测试补齐：`modules/knowledge/backend/tests/test_live_source_filtering.py` 覆盖 list/detail/pipeline；`modules/knowledge/sandbox/test_module.py` 补生命周期契约。

验证：ruff 全绿；`test_live_source_filtering.py` 4 passed；`test_ingest_status_service.py` 9 passed；sandbox 11 passed；probe knowledge health/documents 200；call_capability `knowledge:get_pending_count` 与 `knowledge:search` 200。

未 commit/push。当前 worktree 有其他代理的 backend/app、modules/agent 等越界改动，未触碰、未回退。
