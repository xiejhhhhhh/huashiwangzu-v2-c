---
name: "knowledge-module-sweep-20260703-r2 修复与验证完成"
type: "task"
tags: [knowledge, module-sweep, pipeline, db-audit, validation]
agent: "codex-knowledge-module-sweep-20260703-r2"
created: "2026-07-03T07:07:13.745990+00:00"
---

agent: codex-knowledge-module-sweep-20260703-r2

范围：仅修改 modules/knowledge/**；项目记忆通过工具台写入。工作区存在 codemap/image-gen/office-gen 等其他 agent 脏文件，未改动、未回退。

问题清单：
1. kb_evidence 316 条历史数据全部 chunk_id=0，kb_chunk_entities=0，实体证据链断到 chunk。
2. process_document_entities() 旧路径写 evidence 时没有真实 chunk 关联，也没有写 kb_chunk_entities。
3. get_page_fusion() service 内部未按 owner_id 过滤，router/capability 虽先校验文档，但内部函数可被误用。
4. search cosine_similarity() 在向量维度不一致时 zip 静默截断，可能产生假相似度。
5. find_latest_pipeline_task() 每次全扫 knowledge kb_pipeline 队列并逐条 JSON parse；当前队列量约 1658，状态轮询成本高。
6. DB 存在大量 source unavailable 文档：live kb docs 中大批源文件缺失/删除，历史 fusion_status=done 但源不可用，dashboard/progress 需要显式暴露。
7. entity extraction LLM/JSON 失败被吞成空实体，容易看起来像成功但图谱为空。
8. knowledge 测试目录存在 collection/bootstrap 漂移：缺 backend sys.path/JWT_SECRET、pgvector extension、ASGITransport 不触发生命周期、动态模块加载导致 ORM 重复声明。
9. 历史失败测试留下 dedup/orphan/inflight 等测试文档与上传文件，需要清理。

修复：
- entity_service: extraction 失败返回 errors；legacy block path 写 KbEvidence.chunk_id 到页内首个真实 chunk，并写 KbChunkEntity；fusion entity 重建收集 errors，空实体失败标 degraded；page_fusions/chunks 查询增加 owner_id 过滤；get_page_fusion 支持 owner_id。
- router: /search 与 capability search/get_page_fusion 传 owner_id；block_id 查询按 chunk owner_id 过滤。
- search_service: cosine_similarity 维度不一致时告警并返回 0.0，避免 zip 静默截断。
- ingest_status_service: find_latest_pipeline_task 先用 parameters contains document_id 在 SQL 层收窄，再做 JSON 合同校验。
- models: 为 knowledge ORM 表声明 extend_existing，避免框架动态模块加载与 canonical import 在同一测试进程重复注册表。
- tests: 增加 evidence/chunk_entity 与 page_fusion owner scope 回归；修复 embedding/live-source 测试初始化、pgvector、JWT/backend path、_llm_fuse 签名；新增向量维度不匹配测试。
- 数据清理：清理本轮/历史失败轮次的 knowledge 测试前缀文档与 framework file rows；删除测试上传产物。工具台 SQL 复查 leftover_docs=0。

验证：
- ruff passed: modified knowledge files/tests。
- pytest modules/knowledge/backend/tests: 36 passed, 1 warning。
- pytest modules/knowledge/sandbox/test_module.py: 9 passed。
- call_capability knowledge:search: HTTP 200 success，返回 owner-scoped live results 与 page_fusion。
- call_capability knowledge:get_page_fusion(document_id=1,page=1): HTTP 200 success。
- probe /api/knowledge/dashboard/stats: HTTP 200 success。
- probe /api/knowledge/governance/pipeline-debt/dry-run: HTTP 200 success，matched=500，分类可见。
- SQL leftover test docs: 0。

风险/后续：历史 kb_evidence chunk_id=0 和大量 source_unavailable 文档是既有数据债，本轮修新写入和诊断，不批量迁移/归档历史业务数据。pipeline-debt dry-run 已显示可 archive/retry 分类，真正 apply 需单独授权。
