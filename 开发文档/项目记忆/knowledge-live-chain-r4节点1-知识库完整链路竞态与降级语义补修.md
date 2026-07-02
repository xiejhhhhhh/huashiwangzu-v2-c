---
name: "knowledge-live-chain-r4节点1-知识库完整链路竞态与降级语义补修"
type: "task"
tags: [knowledge-live-chain-r4, knowledge, kb_pipeline, lifecycle, diagnostics, parser-empty, hot-migration, 20260703]
agent: "knowledge-live-chain-r4"
created: "2026-07-02T16:54:43.813705+00:00"
---

## 背景
专项核实知识库完整链路：document/file 生命周期、kb_pipeline enqueue -> orchestrator -> raw_collection -> fusion -> diagnostics schema -> skipped/degraded 语义，并复核历史 failed 债务是否被代码支撑。

## 结论
历史 failed 债务分类接口仍能支撑前序结论：limit=500 dry-run 样本为 source_file_missing=301、source_file_deleted=161、doc_missing=23、file_row_live=13、parser_no_content_blocks=2。核心历史债仍是生命周期债，不应直接清表。

## 本轮发现的真断点
1. 运行中的 kb_pipeline 只在 handler 开始前查一次源文件状态；如果文件在 raw/fusion/profile 长调用期间被删除，orchestrator 可能继续向下游推进，并把 raw/fusion/profile/graph 产物记成完成。
2. source_file_state 原来使用 db.get(File, file_id)，同一 AsyncSession 可能拿到已缓存的 File，跨 session 的 file.deleted 更新无法被及时看见。
3. parser-empty 降级分支 commit 后立即 document_payload(doc)，可能读取过期列触发 SQLAlchemy MissingGreenlet/greenlet_spawn，导致本该 degraded 的 parser-empty 变 failed。
4. knowledge init 的 ALTER TABLE ADD COLUMN IF NOT EXISTS 每次热检查都会参与表强锁竞争；活 pipeline 同时 SELECT 时观测到一次 deadlock。

## 修复
- `source_file_state.get_source_file_availability` 改为 select + populate_existing，强制取数据库最新 File 状态。
- `pipeline_orchestrator` 增加统一 source availability 闸门：run 开始、每个 stage 前、每个 stage 返回后都检查；源不可用时 mark_document_source_unavailable、诊断账本记 skipped、pipeline 返回 skipped，停止后续 stage。
- `document_pipeline_complete` 和 registration payload 在 `parse_error in {source_file_deleted, source_file_missing}` 时不再宣称 search_ready/deep_ready；文件恢复时既有 restore 逻辑会清 parse_error 后复用产物。
- parser-empty 降级分支 commit 后 `await db.refresh(doc)`，再构造 payload。
- `ensure_migration_columns` 先查 information_schema.columns，列已存在就跳过 ALTER，避免重复初始化时无意义争用 AccessExclusiveLock。

## 验证
- `backend/.venv/bin/python -m pytest modules/knowledge/backend/tests/test_pipeline_stage_semantics.py modules/knowledge/backend/tests/test_ingest_status_service.py modules/knowledge/tests/test_raw_collection.py backend/tests/test_knowledge_pipeline_lifecycle.py -q` -> 30 passed。
- `backend/.venv/bin/ruff check modules/knowledge/backend/init_db.py modules/knowledge/backend/services/pipeline_orchestrator.py modules/knowledge/backend/services/source_file_state.py modules/knowledge/backend/services/document_service.py modules/knowledge/backend/tests/test_pipeline_stage_semantics.py modules/knowledge/tests/test_raw_collection.py` -> passed。
- `/api/health` 200 ok，worker 注册 `kb_pipeline`。

## 遗留
活库仍有修复前产生的 `kb_pipeline` running/failed 历史债，例如运行期删除与热迁移 deadlock 样本；本轮未直接改 DB/清队列，后续应走 pipeline-debt dry-run/apply 治理。
