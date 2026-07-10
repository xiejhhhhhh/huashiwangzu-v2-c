# knowledge — 知识库

## Responsibility

Knowledge base module for file registration, parsing pipelines, retrieval, page fusion, entity graph context, and lifecycle governance.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"knowledge"` |
| name | `"知识库"` |
| category | `"AI"` |
| module_type | `"orchestrator"` |
| module_family | `"knowledge"` |
| product_status | `"core"` |
| window_type | `"normal"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `true` |
| show_on_desktop | `true` |
| route_prefix | `"/api/knowledge"` |
| contract_version | `"2.0"` |
| module_version | `"1.0.0"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/knowledge` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/knowledge`

| Family | Methods | Purpose |
|---|---|---|
| `chunks` | GET | Endpoint family under `/api/knowledge` |
| `dashboard` | GET | Endpoint family under `/api/knowledge` |
| `documents` | DELETE/GET/POST | Endpoint family under `/api/knowledge` |
| `entities` | GET | Endpoint family under `/api/knowledge` |
| `entity-graph` | GET | Endpoint family under `/api/knowledge` |
| `governance` | GET/POST | Endpoint family under `/api/knowledge` |
| `health` | GET | Endpoint family under `/api/knowledge` |
| `relation-graph` | GET | Endpoint family under `/api/knowledge` |
| `search` | POST | Endpoint family under `/api/knowledge` |

## Status Contract

Queue status and document readiness are different contracts.

- `framework_system_task_queues.status=completed` only means one worker task exited.
- User-facing readiness must use document stage fields:
  `raw_status`, `fusion_status`, `profile_status`, `graph_status`, `relation_status`.
- Deep analysis is complete only when all five stage fields are `done`.
- `pending` work is normal waiting work, not skipped work.
- Active queue rows are surfaced as `queued` / `running`; stages blocked by worker pause config are surfaced as `paused`.
- `degraded` is partial completion and must be shown as warning, not success.
- Dashboard stats expose `completed_documents` for deep completion and
  separate `queued_documents`, `paused_documents`, `waiting_documents`,
  `partial_documents`, and `failed_documents` counts.

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 32

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `apply_pipeline_debt` | `admin` | `action`, `categories`, `category`, `category_limits`, `dry_run`, `limit`, `limit_each`, `order`, `task_ids` | dry-run 或 guarded apply 历史知识库管道债治理动作 |
| `archive_source_unavailable_documents` | `admin` | `audit_reason`, `confirm`, `dry_run`, `limit`, `reason` | dry-run 或确认归档源文件不可用的知识库文档 |
| `audit_lifecycle_debt` | `admin` | `limit`, `reason` | 审计源文件已删除、缺失、路径异常或磁盘文件缺失的 active 知识库文档 |
| `backfill_chunk_embeddings` | `admin` | `batch_size`, `dry_run`, `embedding_profile`, `limit` | dry-run 或补跑版本化块向量到边车向量表 |
| `backfill_cognitive_v3` | `admin` | `build_terms`, `dry_run`, `limit`, `source_root` | 回填知识库 V3 内容复用链路、批次验收报告和可选认知派生索引 |
| `backfill_derived_governance` | `admin` | `dry_run`, `include_conclusion_evidence`, `include_disambiguation`, `include_entity_aliases`, `include_lineage`, `limit` | 从已有分析产物、事实候选和实体词典回填知识库派生治理索引 |
| `classify_pipeline_debt` | `admin` | `categories`, `category`, `category_limits`, `limit`, `limit_each`, `order`, `task_ids` | dry-run 分类历史知识库管道债，不修改队列 |
| `derive_cognitive_index` | `admin` | `document_id`, `limit` | 按单文档重建 V3 词项、事实和因果候选派生索引 |
| `enqueue_enterprise_source_import` | `admin` | `batch_size`, `extensions`, `priority`, `skip_existing_md5`, `source_root`, `target_root_name` | 将企业源目录扫描投递到后台队列，按文件任务导入并触发知识库分析 |
| `enqueue_source_manifest_import` | `admin` | `extensions`, `limit`, `priority`, `skip_existing_md5`, `source_root`, `target_root_name` | 从外部源清单中投递尚未进入导入队列的文件 |
| `enqueue_incomplete_documents` | `admin` | `dry_run`, `extensions`, `include_search_incomplete`, `limit`, `priority` | 预览或补排未完成深层知识分析的文档 |
| `export` | `viewer` | `document_id`, `format` | 导出已解析文档（markdown/html/json） |
| `get_block` | `viewer` | `block_id` | 按 block_id 获取内容块详情 |
| `get_chunk_embedding_counts` | `admin` | `embedding_profile` | 统计指定向量模型 profile 的块向量边车覆盖率 |
| `get_derived_governance_counts` | `admin` | none | 统计当前用户的知识库派生治理索引行数 |
| `get_entity_dictionary` | `viewer` | `keyword` | 查询实体词典 |
| `get_evidence_detail` | `viewer` | `entity_id` | 获取证据详情 |
| `get_graph_context` | `viewer` | `entity_id` | 查询图谱上下文 |
| `get_ingest_status` | `viewer` | `document_id` | 查询文档入库任务与分析阶段状态 |
| `get_ocr_words` | `viewer` | `file_id`, `page` | 获取 PDF OCR 词坐标 |
| `get_page_fusion` | `viewer` | `document_id`, `page` | 获取页级融合内容 |
| `get_pending_count` | `viewer` | none | 获取待确认数量（治理用） |
| `import_enterprise_source_batch` | `admin` | `dry_run`, `extensions`, `limit`, `skip_existing_md5`, `source_root`, `target_root_name` | dry-run 或限量导入企业源目录文件并触发知识库分析 |
| `ingest` | `editor` | `file_id` | 将文件注册到知识库并触发分析 |
| `plan_pipeline_rerun` | `admin` | `document_id`, `reason`, `stage` | dry-run 规划知识库管道重跑，不修改队列或产物 |
| `reconcile_orphan_pipeline_runs` | `admin` | `dry_run`, `limit`, `run_ids` | dry-run 或 guarded apply 收口无 task_id 的 orphan running 诊断运行 |
| `reconcile_pending_pipeline_queue` | `admin` | `categories`, `category`, `category_limits`, `dry_run`, `limit`, `limit_each`, `order`, `task_ids` | dry-run 或归档已不可执行的 pending 知识库管道队列任务，保留仍可执行的 live pending |
| `reconcile_running_pipeline_queue` | `admin` | `categories`, `category`, `category_limits`, `dry_run`, `limit`, `limit_each`, `order`, `task_ids` | dry-run 或恢复中断的 running 知识库管道队列任务，live 任务回 pending，obsolete 任务归档 skipped |
| `reflect_retrieval_feedback` | `admin` | `conversation_excerpt`, `query_context_id` | 根据后续对话片段复盘一次知识库检索的隐式反馈 |
| `scan_source_manifest` | `admin` | `extensions`, `limit`, `mark_missing`, `source_root`, `target_root_name` | 扫描外部物理源目录到持久清单，不直接导入文件 |
| `search` | `viewer` | `embedding_profile`, `query`, `top_k` | 按关键词搜索知识库，返回相关块 |
| `source_manifest_summary` | `admin` | `source_root` | 按来源、扩展名和导入状态汇总外部源清单 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `kb_analysis_artifacts` | Owned by `knowledge` module |
| `kb_artifact_lineage` | Owned by `knowledge` module |
| `kb_catalogs` | Owned by `knowledge` module |
| `kb_chunk_entities` | Owned by `knowledge` module |
| `kb_chunks` | Owned by `knowledge` module |
| `kb_conclusion_evidence` | Owned by `knowledge` module |
| `kb_causal_candidates` | Owned by `knowledge` module |
| `kb_content_objects` | Owned by `knowledge` module |
| `kb_disambiguation` | Owned by `knowledge` module |
| `kb_document_profiles` | Owned by `knowledge` module |
| `kb_document_profile_vectors` | Owned by `knowledge` module |
| `kb_documents` | Owned by `knowledge` module |
| `kb_entity_aliases` | Owned by `knowledge` module |
| `kb_entity_dictionary` | Owned by `knowledge` module |
| `kb_entity_merge_log` | Owned by `knowledge` module |
| `kb_evidence` | Owned by `knowledge` module |
| `kb_fact_candidates` | Owned by `knowledge` module |
| `kb_file_knowledge_links` | Owned by `knowledge` module |
| `kb_file_relations` | Owned by `knowledge` module |
| `kb_governance_candidates` | Owned by `knowledge` module |
| `kb_graph_edges` | Owned by `knowledge` module |
| `kb_graph_nodes` | Owned by `knowledge` module |
| `kb_image_assets` | Owned by `knowledge` module |
| `kb_image_similar_pairs` | Owned by `knowledge` module |
| `kb_image_similarity_groups` | Owned by `knowledge` module |
| `kb_ingest_batches` | Owned by `knowledge` module |
| `kb_page_fusions` | Owned by `knowledge` module |
| `kb_pipeline_runs` | Owned by `knowledge` module |
| `kb_pipeline_stage_runs` | Owned by `knowledge` module |
| `kb_pipeline_stale` | Owned by `knowledge` module |
| `kb_query_contexts` | Owned by `knowledge` module |
| `kb_raw_data` | Owned by `knowledge` module |
| `kb_retrieval_learning_events` | Owned by `knowledge` module |
| `kb_source_file_manifest` | Owned by `knowledge` module |
| `kb_term_edges` | Owned by `knowledge` module |
| `kb_term_occurrences` | Owned by `knowledge` module |
| `kb_terms` | Owned by `knowledge` module |
| `kb_validation_reports` | Owned by `knowledge` module |

Use `db_schema()` for live database details. This module must not directly read or write other modules' tables.

## Analysis Artifacts And Image Similarity

- `kb_analysis_artifacts` is an append-only stage ledger for pipeline traceability and dry-run rerun planning.
- Evidence rows may carry lineage back to raw data, page fusion, artifacts, prompt hash, model used, and diagnostics.
- `page_render` materializes reusable visual page assets before OCR/VLM stages. Page images are rendered, compressed, stored on disk, and recorded in `kb_image_assets`; `raw_ocr` and `raw_vision` consume those assets instead of rendering the source document again.
- Image similarity is a sidecar stage for PDF page renders and image files. It stores perceptual hashes, suspected/high pairs, and groups, but it does not skip VLM analysis or reuse representative-image VLM output.
- Chaotic model-returned tags, entity types, and relation types are preserved as raw business signals until a later governance phase.

## V3 Cognitive Substrate

- V3 is additive on PostgreSQL/pgvector and the current `kb_*` pipeline; it does not replace the storage engine, vector index, parser, or model gateway.
- `kb_content_objects` and `kb_file_knowledge_links` make duplicate-file reuse explicit. Multiple file records may point to one canonical knowledge document without copying chunks, raw data, fusion pages, or profile rows.
- `kb_ingest_batches` and `kb_validation_reports` record batch-level coverage, duplicate counts, missing canonical mappings, and validation findings for enterprise imports.
- `kb_document_profile_vectors` is the indexed document-profile vector sidecar for relation candidate recall. `relations` first combines pgvector semantic TopK and entity-inverted candidates, then keeps the existing exact cosine/Jaccard scoring before writing `kb_file_relations`.
- `kb_terms`, `kb_term_occurrences`, `kb_term_edges`, `kb_fact_candidates`, `kb_causal_candidates`, and `kb_query_contexts` are rebuildable derived indexes. They preserve chaotic model/business signals for later governance instead of freezing a premature taxonomy.
- `kb_retrieval_learning_events` stores implicit retrieval feedback inferred from later conversation excerpts. Search uses it as a bounded ranking prior, while hard evidence, graph signals, source quality, and fusion verification remain the main scoring signals.
- `cognitive_index` is the durable per-document DAG stage that fills the rebuildable V3 term, occurrence, co-occurrence, fact-candidate, and causal-candidate indexes from existing page fusion and document profile outputs.
- `backfill_cognitive_v3` is dry-run by default. `derive_cognitive_index` can rebuild one document's V3 derived layer from existing page fusion and document profile outputs without rerunning raw/VLM/LLM stages.

## Queue Governance

- Runtime knowledge analysis uses one queue task type: `kb_pipeline_stage`. Each row runs one durable DAG stage and enqueues newly unblocked downstream stages.
- Legacy `kb_pipeline` rows are historical debt only. Debt governance can classify/retry/archive legacy rows and current `kb_pipeline_stage` rows, but new execution never emits `kb_pipeline`.
- Pending live pipeline rows are executable queue head items. `reconcile_pending_pipeline_queue` archives only obsolete pending rows whose document is gone, file row is deleted/missing, storage path is invalid, or physical source file is missing, while leaving live pending work in place.
- Running task recovery is handled by the framework task worker timeout logic; knowledge-specific orphan diagnostics remain available through `reconcile_orphan_pipeline_runs`.

## Cross-Module Dependencies

- Manifest dependencies are declared in `manifest.json` when needed.
- Runtime calls to other modules must use framework capability calls, not imports or direct DB reads.

## File Access / Permission Boundary

If this module consumes `file_id`, it must validate file access through framework file access helpers or an approved public capability before reading disk.

## Frontend File Tree Loading Contract

- The Knowledge file tree loads by folder scope. Opening the app loads only the root folder via `/files/list`; expanding a folder loads only that folder's direct children.
- Knowledge status is joined only for the visible folder children through `/knowledge/documents/by-files`, capped at 200 file ids per request.
- Opening the Knowledge app must not scan the full desktop tree, load every knowledge document, auto-register every supported file, or enqueue analysis for files the user has not opened.
- Registering a file into Knowledge is a user-driven action from opening that file node; search and relation jumps may fetch a single document by `document_id` without loading the full library.

## Frontend / Backend Structure

| Path | Status |
|---|---|
| `frontend/index.vue` | present |
| `runtime/index.ts` | present |
| `backend/router.py` | present |
| `sandbox/test_module.py` | present |
| `sandbox/package.json` | present |

## Acceptance

<!-- DOCS-SYNC: section=sandbox -->
| Area | Status | Verification |
|---|---|---|
| README | PASS | `modules/knowledge/README.md` |
| Acceptance matrix | PASS | present |
| Backend sandbox | PASS | `PYTHONPATH=backend /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/backend/.venv/bin/python modules/knowledge/sandbox/test_module.py` |
| Frontend sandbox | PASS | `cd modules/knowledge/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module knowledge --check` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/knowledge/sandbox/test_module.py
cd modules/knowledge/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module knowledge --check
```

## Boundaries

- Keep module business code and data inside `modules/knowledge/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
