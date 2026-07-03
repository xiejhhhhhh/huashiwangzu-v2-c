---
name: "knowledge 文件生命周期只读审计 r3"
type: "task"
tags: [knowledge, audit, file-lifecycle, pipeline-debt, read-only]
agent: "knowledge-file-lifecycle-audit-r3"
created: "2026-07-03T10:06:24.581122+00:00"
---

# 我是谁
knowledge-file-lifecycle-audit-r3

# 做了什么
只读审计 knowledge 文件生命周期和历史 kb_pipeline 失败债务。未修改业务代码、未修改数据库、未提交。

# 关键证据
- CodeGraph/源码：`modules/knowledge/backend/services/search_service.py` 的 `_live_chunk_select()` 通过 `KbDocument -> framework_file_items` 内连接并过滤 `KbDocument.deleted=false`、`File.deleted=false`，search/chunks/block 主检索路径能过滤 missing/deleted 源文件。
- CodeGraph/源码：`modules/knowledge/backend/services/document_service.py` 的 `list_documents()`、`get_document()` 只过滤 `KbDocument.deleted=false` 和 owner，不校验 source file live；`router.py` 的 document detail/list 直接使用它们。
- CodeGraph/源码：`modules/knowledge/backend/services/pipeline_service.py` 在 `_run_pipeline()` 中先 `parse_and_index_document()`，再进入 orchestrator；source file 在这之后才被 orchestrator 再次检查，存在先写 chunks/raw/fusion 后 skipped 的顺序缺口。
- DB：`kb_documents=1412`，其中源文件 missing=910、source deleted=449、source live=53；未删除但源文件 unavailable 的文档=1268。
- DB：`kb_chunks=1162`，其中挂在 source missing/deleted 上的 chunk=1095，live 可见 chunk=67。
- DB：`framework_system_task_queues` 中 knowledge/kb_pipeline failed=769；错误标记：File not found=710，Document not found=23，Parser empty=17，other=19。
- 活接口：`GET /api/knowledge/documents?page=1&page_size=10` 返回 `parse_error=source_file_deleted` 的文档（样本 document_id=1421）。同一文档 detail 200；progress/ingest-status 标 `source_unavailable`；chunks/fusions 404；search/capability search 未返回该 deleted-source 文档。
- pipeline debt dry-run：500 条样本分类为 source_file_missing=301、source_file_deleted=161、doc_missing=23、file_row_live=13、parser_no_content_blocks=2。

# P0/P1/P2
P0：文档 list/detail 仍暴露源文件已删除/缺失的 knowledge 文档壳，且可显示 done 状态字段，和 README 中“source unavailable 不得继续计入完成”的契约冲突。修复边界在 `modules/knowledge/backend/services/document_service.py` 和 `router.py`，不要改框架。

P1：pipeline 的源文件检查顺序不够早，可能先写 chunks/raw/fusion 后再 skipped，导致脏产物累积。修复边界在 `modules/knowledge/backend/services/pipeline_service.py`，在 parse/index 前检查 source availability，并在相关入口统一 live gate。

P1：历史 kb_pipeline failed 中 File not found/Document not found 主要是生命周期缺口造成的可归档债务，不应长期算 failed。已有 dry-run/apply 治理服务，但尚未执行；修复/治理边界在 `pipeline_debt_service.py`，先 dry-run 后人工确认 apply。

P2：空库/脏库治理。空表：kb_catalogs、kb_chunk_entities、kb_conclusion_evidence、kb_disambiguation、kb_entity_aliases、kb_entity_merge_log。脏库：kb_raw_data/page_fusions/profiles/governance/file_relations/stale 大量挂 source unavailable。owner 均为 knowledge 模块；framework_file_items 属框架文件系统。建议补只读审计接口或治理 dry-run，不直接物理清库。

# 关联 commit
无，本次只读审计未提交。
