---
name: "R5 knowledge source-unavailable 状态机 ready 收口"
type: "task"
tags: [knowledge, R5, source_unavailable, ingest_status, tests]
agent: "codex-r5-knowledge-source-unavailable-a"
created: "2026-07-03T11:53:01.649707+00:00"
---

任务：R5 第一阶段任务信 A，修复 knowledge 源文件 missing/deleted 文档在 ingest/status/search/deep readiness 上被历史 done 阶段误判完成的问题。

改动：
- 在 modules/knowledge/backend/services/document_service.py 增加 document_source_unavailable_reason(doc)，统一识别 parse_error=source_file_missing/source_file_deleted。
- document_parse_allows_search() 和 document_pipeline_complete() 遇 source unavailable 直接返回 False；document_pipeline_complete 新增 source_available guard，供已知 File 行状态的调用路径显式短路。
- document_registration_payload() 遇 source unavailable 对外返回 status/pipeline_status=source_unavailable、stage=source，search_ready/deep_ready=false。
- modules/knowledge/backend/services/ingest_status_service.py 将文档持久 source-unavailable 标记与 File 行 missing/deleted 的 source_available/source_state 合并；source unavailable 时 parse/vector/raw/fusion/profile/graph/relation ready 均为 false，last_error 返回 source_file_missing/source_file_deleted。
- modules/knowledge/backend/tests/test_ingest_status_service.py 增加历史 done + source_file_missing、DB source_file_deleted、正常 done 仍 ready、document_pipeline_complete source guard 的覆盖。

验证：
- ruff check: document_service.py、ingest_status_service.py、test_ingest_status_service.py 全绿。
- pytest modules/knowledge/backend/tests/test_ingest_status_service.py: 11 passed。
- pytest modules/knowledge/backend/tests/test_live_source_filtering.py: 4 passed。
- pytest modules/knowledge/backend/tests/test_pipeline_stage_semantics.py: 12 passed。
- pytest modules/knowledge/backend/tests/test_pipeline_debt_service.py: 11 passed。
- pytest modules/knowledge/backend/tests: 52 passed, 1 个无关 github-search FastAPI deprecation warning。
- 只读活栈 dry-run: knowledge:classify_pipeline_debt(limit=5) 成功，仍显示 status_doc_source_file_missing=845、status_doc_source_file_deleted=440 的生产存量样本；未执行 apply/reconcile。
- 只读 SQL 验证样本 1589 为 File row missing 且 parse/vector/raw/fusion=done、parse_error=source_file_missing；样本 1625 为 File row deleted 且 parse/vector/raw/fusion=done、parse_error=source_file_deleted。

残留风险：
- 本次按任务边界没有修改 pipeline_debt_service.py 的 apply/reconcile 逻辑，也没有对 1285 条生产存量做数据修复；问题队列计数需要 B/C 泳道或后续治理动作收敛。
- 活栈 get_ingest_status 对样本 1589 通过能力入口返回 404，未绕过权限；本次主要验证依赖单测和只读 SQL/dry-run。

生产数据改动：无。commit=无。
