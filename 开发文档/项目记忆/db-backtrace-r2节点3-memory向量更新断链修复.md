---
name: "db-backtrace-r2节点3-memory向量更新断链修复"
type: "task"
tags: [db-backtrace, memory, embedding, pgvector, fix, 20260703]
agent: "db-backtrace-worker-r2"
created: "2026-07-02T16:18:46.943251+00:00"
---

节点3：形成完整链路问题并已修复。反向审计发现 memory_records 有 37 条但 with_embedding 仅 4、memory_links 为 0；memory 日志显示 post-save embedding 更新多次失败：`UPDATE memory_records SET embedding = :embedding::vector WHERE id = $1` 在 asyncpg 下报 syntax error near ':'。根因是 SQLAlchemy text 绑定参数与 PostgreSQL `::vector` cast 拼接后未被正确解析。修复范围仅 memory 模块：`modules/memory/backend/services/embedding_service.py` 将 SQL 改为 `CAST(:embedding AS vector(1024))`，并在 `modules/memory/sandbox/test_module.py` 增加回归，禁止 `:embedding::vector` 回潮。验证：memory sandbox 21 passed；backend tests `test_memory_core_paths.py` + `test_empty_flow_audit_regressions.py` 42 passed；ruff 两个改动文件通过；只读 SQL `SELECT CAST(:embedding AS vector(1024))` 在当前 asyncpg/pgvector 栈通过。
