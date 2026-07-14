# memory — 记忆

Long-term memory module for facts, semantic recall, memory links, experience records, stable rules, and dream/rethink maintenance.

## 对外能力

| 能力 | 说明 |
|------|------|
| `backfill_chunk_embeddings` | Admin governance: safely backfill missing memory_chunk embeddings with dry-run support |
| `backfill_embeddings` | Admin governance: safely backfill missing memory record embeddings with dry-run, owner, limit, and optional dream linking |
| `backfill_links` | Admin governance: backfill missing memory_links between existing memory records using vector similarity. Dry-run safe. |
| `delete` | 删除一条记忆 |
| `dream` | 触发记忆自优化（去重合并 + 建链 + 衰减），后台运行不阻塞 |
| `experience_feedback` | 反馈经验执行结果：成功则权重 +1，失败则失败次数 +1 并记录注释 |
| `fuse` | 将多条记忆融合成贴合查询的一段简报（即时融合，on-demand） |
| `insert` | 向已有记忆追加内容 |
| `list` | 列出自己所有的记忆 |
| `match_experience` | 在 SQL principal 可见并集内召回 contract 仍兼容的结构化成功经验 |
| `overview_stats` | Admin overview: aggregated memory & experience statistics (total_count, with_embedding, avg_confidence, link_count, experience counts, etc.) |
| `recall` | 语义检索自己的记忆（向量语义召回 + 重排 + 可选顺链扩展），不再仅靠关键词 |
| `recall_chunk` | 语义检索 chunk 级记忆（带 provenance 溯源信息），返回最小粒度段落 |
| `recall_stable_rules` | 获取当前用户所有活跃的稳定规则记忆（项目边界、用户偏好、硬约束等），按优先级降序返回 |
| `replace` | 替换记忆中的某段文本（精确片段替换） |
| `rethink` | 整条重写一条记忆（自编辑工具，如用户纠正错误时） |
| `save` | 保存一段记忆（事实/偏好/约定），自动提取摘要和向量用于语义检索 |
| `review_experience` | 审核达到晋升门槛的高风险共享经验候选；批准后才可进入召回 |
| `save_experience` | 保存结构化成功经验；自动脱敏、绑定 capability contract，并按 principal 生成分层候选 |
| `save_stable_rule` | 保存一条稳定规则记忆（项目边界/用户偏好/硬约束/长期规则），不参与向量衰减 |

## 接口

后端前缀：`/api/memory`

| 路径族 | 方法 |
|------|------|
| /delete | POST |
| /dream | POST |
| /fuse | POST |
| /insert | POST |
| /list | GET |
| /recall | POST |
| /replace | POST |
| /rethink | POST |
| /save | POST |

## 数据表

| 表名 |
|------|
| `memory_chunks` |
| `memory_experiences` |
| `memory_links` |
| `memory_records` |
| `memory_stable_rules` |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/memory/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module memory --check
```
