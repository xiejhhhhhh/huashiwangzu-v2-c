# knowledge — 知识库

Knowledge base module for file registration, parsing pipelines, retrieval, page fusion, entity graph context, and lifecycle governance.

## 对外能力

| 能力 | 说明 |
|------|------|
| `apply_pipeline_debt` | dry-run 或 guarded apply 历史知识库管道债治理动作 |
| `archive_source_unavailable_documents` | dry-run 或确认归档源文件不可用的知识库文档 |
| `audit_lifecycle_debt` | 审计源文件已删除、缺失、路径异常或磁盘文件缺失的 active 知识库文档 |
| `backfill_chunk_embeddings` | dry-run 或补跑版本化块向量到边车向量表 |
| `backfill_cognitive_index` | 回填知识库内容复用链路、批次验收报告和可选认知派生索引 |
| `backfill_derived_governance` | 从已有分析产物、事实候选和实体词典回填知识库派生治理索引 |
| `classify_pipeline_debt` | dry-run 分类历史知识库管道债，不修改队列 |
| `derive_cognitive_index` | 按单文档重建词项、事实和因果候选派生索引 |
| `enqueue_chunk_embedding_backfill` | 把 Qwen3 块向量边车补跑加入后台队列，worker 按需拉起本地模型 |
| `enqueue_enterprise_source_import` | 将企业源目录扫描投递到后台队列，按文件任务导入并触发知识库分析 |
| ... | 等 34 个能力 |

## 接口

后端前缀：`/api/knowledge`

| 路径族 | 方法 |
|------|------|
| /chunks | GET |
| /dashboard | GET |
| /documents | DELETE/GET/POST |
| /entities | GET |
| /entity-graph | GET |
| /governance | GET/POST |
| /health | GET |
| /relation-graph | GET |
| /search | POST |

## 数据表

| 表名 |
|------|
| `kb_analysis_artifacts` |
| `kb_artifact_lineage` |
| `kb_catalogs` |
| `kb_chunk_entities` |
| `kb_chunks` |
| `kb_conclusion_evidence` |
| `kb_causal_candidates` |
| `kb_content_objects` |
| `kb_disambiguation` |
| `kb_document_profiles` |
| `kb_document_profile_vectors` |
| `kb_documents` |
| `kb_entity_aliases` |
| `kb_entity_dictionary` |
| `kb_entity_merge_log` |
| `kb_evidence` |
| `kb_fact_candidates` |
| `kb_file_knowledge_links` |
| `kb_file_relations` |
| `kb_governance_candidates` |
| `kb_graph_edges` |
| `kb_graph_nodes` |
| `kb_image_assets` |
| `kb_image_similar_pairs` |
| `kb_image_similarity_groups` |
| `kb_ingest_batches` |
| `kb_page_fusions` |
| `kb_pipeline_runs` |
| `kb_pipeline_stage_runs` |
| `kb_pipeline_stale` |
| `kb_query_contexts` |
| `kb_raw_data` |
| `kb_retrieval_learning_events` |
| `kb_source_file_manifest` |
| `kb_term_edges` |
| `kb_term_occurrences` |
| `kb_terms` |
| `kb_validation_reports` |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/knowledge/sandbox/test_module.py
cd modules/knowledge/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module knowledge --check
```
