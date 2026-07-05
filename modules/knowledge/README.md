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
| window_type | `"normal"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `true` |
| show_on_desktop | `true` |
| route_prefix | `"/api/knowledge"` |
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

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 16

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `apply_pipeline_debt` | `admin` | `action`, `categories`, `category`, `category_limits`, `dry_run`, `limit`, `limit_each`, `order`, `task_ids` | dry-run 或 guarded apply 历史知识库管道债治理动作 |
| `archive_source_unavailable_documents` | `admin` | `audit_reason`, `confirm`, `dry_run`, `limit`, `reason` | dry-run 或确认归档源文件不可用的知识库文档 |
| `audit_lifecycle_debt` | `admin` | `limit`, `reason` | 审计源文件已删除或缺失的 active 知识库文档 |
| `classify_pipeline_debt` | `admin` | `categories`, `category`, `category_limits`, `limit`, `limit_each`, `order`, `task_ids` | dry-run 分类历史知识库管道债，不修改队列 |
| `export` | `viewer` | `document_id`, `format` | 导出已解析文档（markdown/html/json） |
| `get_block` | `viewer` | `block_id` | 按 block_id 获取内容块详情 |
| `get_entity_dictionary` | `viewer` | `keyword` | 查询实体词典 |
| `get_evidence_detail` | `viewer` | `entity_id` | 获取证据详情 |
| `get_graph_context` | `viewer` | `entity_id` | 查询图谱上下文 |
| `get_ingest_status` | `viewer` | `document_id` | 查询文档入库任务与分析阶段状态 |
| `get_ocr_words` | `viewer` | `file_id`, `page` | 获取 PDF OCR 词坐标 |
| `get_page_fusion` | `viewer` | `document_id`, `page` | 获取页级融合内容 |
| `get_pending_count` | `viewer` | none | 获取待确认数量（治理用） |
| `ingest` | `editor` | `file_id` | 将文件注册到知识库并触发分析 |
| `reconcile_orphan_pipeline_runs` | `admin` | `dry_run`, `limit`, `run_ids` | dry-run 或 guarded apply 收口无 task_id 的 orphan running 诊断运行 |
| `search` | `viewer` | `query`, `top_k` | 按关键词搜索知识库，返回相关块 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `kb_catalogs` | Owned by `knowledge` module |
| `kb_chunk_entities` | Owned by `knowledge` module |
| `kb_chunks` | Owned by `knowledge` module |
| `kb_conclusion_evidence` | Owned by `knowledge` module |
| `kb_disambiguation` | Owned by `knowledge` module |
| `kb_document_profiles` | Owned by `knowledge` module |
| `kb_documents` | Owned by `knowledge` module |
| `kb_entity_aliases` | Owned by `knowledge` module |
| `kb_entity_dictionary` | Owned by `knowledge` module |
| `kb_entity_merge_log` | Owned by `knowledge` module |
| `kb_evidence` | Owned by `knowledge` module |
| `kb_file_relations` | Owned by `knowledge` module |
| `kb_governance_candidates` | Owned by `knowledge` module |
| `kb_graph_edges` | Owned by `knowledge` module |
| `kb_graph_nodes` | Owned by `knowledge` module |
| `kb_page_fusions` | Owned by `knowledge` module |
| `kb_pipeline_runs` | Owned by `knowledge` module |
| `kb_pipeline_stage_runs` | Owned by `knowledge` module |
| `kb_pipeline_stale` | Owned by `knowledge` module |
| `kb_raw_data` | Owned by `knowledge` module |

Use `db_schema()` for live database details. This module must not directly read or write other modules' tables.

## Cross-Module Dependencies

- Manifest dependencies are declared in `manifest.json` when needed.
- Runtime calls to other modules must use framework capability calls, not imports or direct DB reads.

## File Access / Permission Boundary

If this module consumes `file_id`, it must validate file access through framework file access helpers or an approved public capability before reading disk.

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
| Manifest contract | PASS | `modules/knowledge/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="knowledge", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/knowledge/sandbox/test_module.py` |
| Frontend sandbox | PASS | `cd modules/knowledge/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module knowledge --check` |
| Known debt | PASS | None |
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
