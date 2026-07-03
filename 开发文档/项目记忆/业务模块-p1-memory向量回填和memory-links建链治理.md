---
name: "业务模块-P1-Memory向量回填和memory_links建链治理"
type: task
tags: ["memory", "backfill", "vector", "links", "embedding", "P1", "业务模块"]
created: 2026-07-03
agent: opencode
---

## 做了什么

修复 Memory 模块的向量回填和 memory_links 建链缺失。

### 3 项修复

1. **新增 `_auto_link_memory()`** — 在 `_post_save_process` 末尾调用，新记忆保存/更新后自动建链（语义相似 ≥ 0.55）。修复了 raw SQL 返回 string 类型、session identity map 过期等坑。

2. **新增 `memory:backfill_links` 治理能力** — admin 可批量补建已有记录间的缺失链接，支持 dry_run 预览（1-500 条/批）。

3. **新增 `memory:backfill_chunk_embeddings` 治理能力** — admin 可批次回填 memory_chunks 缺失向量。

### 修复成果

- memory_records 有向量数：4 → 19（凭 backfill_embeddings + dream 补回）
- memory_links：0 → 58（dream 建链 52 条 + 自动建链 6 条）
- memory_chunks：12 条全部有向量
- 新记忆保存自动建链已验证通过（新记忆自动关联 5 条语义相近记忆）

### 踩坑
- pgvector raw SQL `SELECT embedding` 返回的是 `str` 类型（vector 的文本表示），需要 `strip("[]").split(",")` 转 float 数组，不能直接 `for v in vec` 迭代
- SQLAlchemy `expire_on_commit=True` 默认 expire ORM 属性，在 commit 后访问属性会触发 async lazy load 失败，需提前捕获值
