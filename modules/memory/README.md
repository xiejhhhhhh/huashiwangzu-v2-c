# memory — 记忆

## Responsibility

Long-term memory module for facts, semantic recall, memory links, experience records, stable rules, and dream/rethink maintenance.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"memory"` |
| name | `"记忆"` |
| category | `"tools"` |
| module_type | `"service"` |
| module_family | `"agent"` |
| product_status | `"background"` |
| window_type | `"normal"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/memory"` |
| contract_version | `"2.0"` |
| module_version | `"1.0.0"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/memory` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/memory`

| Family | Methods | Purpose |
|---|---|---|
| `delete` | POST | Endpoint family under `/api/memory` |
| `dream` | POST | Endpoint family under `/api/memory` |
| `fuse` | POST | Endpoint family under `/api/memory` |
| `insert` | POST | Endpoint family under `/api/memory` |
| `list` | GET | Endpoint family under `/api/memory` |
| `recall` | POST | Endpoint family under `/api/memory` |
| `replace` | POST | Endpoint family under `/api/memory` |
| `rethink` | POST | Endpoint family under `/api/memory` |
| `save` | POST | Endpoint family under `/api/memory` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 19

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `backfill_chunk_embeddings` | `admin` | `dry_run`, `limit`, `owner_id` | Admin governance: safely backfill missing memory_chunk embeddings with dry-run support |
| `backfill_embeddings` | `admin` | `dry_run`, `limit`, `owner`, `owner_id`, `run_dream` | Admin governance: safely backfill missing memory record embeddings with dry-run, owner, limit, and optional dream linking |
| `backfill_links` | `admin` | `dry_run`, `limit`, `owner_id` | Admin governance: backfill missing memory_links between existing memory records using vector similarity. Dry-run safe. |
| `delete` | `viewer` | `id` | 删除一条记忆 |
| `dream` | `editor` | none | 触发记忆自优化（去重合并 + 建链 + 衰减），后台运行不阻塞 |
| `experience_feedback` | `viewer` | `experience_id`, `note`, `success`, `team_owner_ids` | 反馈经验执行结果：成功则权重 +1，失败则失败次数 +1 并记录注释 |
| `fuse` | `viewer` | `ids`, `query` | 将多条记忆融合成贴合查询的一段简报（即时融合，on-demand） |
| `insert` | `viewer` | `id`, `text` | 向已有记忆追加内容 |
| `list` | `viewer` | `limit`, `offset` | 列出自己所有的记忆 |
| `match_experience` | `viewer` | `limit`, `query`, `team_owner_ids` | 语义匹配当前用户输入相关的成功经验（纯语义，零硬编码规则） |
| `overview_stats` | `admin` | none | Admin overview: aggregated memory & experience statistics (total_count, with_embedding, avg_confidence, link_count, experience counts, etc.) |
| `recall` | `viewer` | `expand_chain`, `limit`, `query` | 语义检索自己的记忆（向量语义召回 + 重排 + 可选顺链扩展），不再仅靠关键词 |
| `recall_chunk` | `viewer` | `limit`, `query` | 语义检索 chunk 级记忆（带 provenance 溯源信息），返回最小粒度段落 |
| `recall_stable_rules` | `viewer` | `rule_types` | 获取当前用户所有活跃的稳定规则记忆（项目边界、用户偏好、硬约束等），按优先级降序返回 |
| `replace` | `viewer` | `id`, `new_text`, `old_text` | 替换记忆中的某段文本（精确片段替换） |
| `rethink` | `viewer` | `id`, `tags`, `text` | 整条重写一条记忆（自编辑工具，如用户纠正错误时） |
| `save` | `viewer` | `source`, `tags`, `text` | 保存一段记忆（事实/偏好/约定），自动提取摘要和向量用于语义检索 |
| `save_experience` | `viewer` | `scope`, `source_conversation_id`, `steps`, `tools_used`, `trigger_condition` | 保存一条成功经验（包含触发条件、有序步骤、工具列表），自动向量化并去重 |
| `save_stable_rule` | `viewer` | `content`, `priority`, `rule_type`, `source` | 保存一条稳定规则记忆（项目边界/用户偏好/硬约束/长期规则），不参与向量衰减 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `memory_chunks` | Owned by `memory` module |
| `memory_experiences` | Owned by `memory` module |
| `memory_links` | Owned by `memory` module |
| `memory_records` | Owned by `memory` module |
| `memory_stable_rules` | Owned by `memory` module |

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
| `sandbox/package.json` | not present |

## Acceptance

<!-- DOCS-SYNC: section=sandbox -->
| Area | Status | Verification |
|---|---|---|
| README | PASS | `modules/memory/README.md` |
| Acceptance matrix | PASS | present |
| Backend sandbox | PASS | `PYTHONPATH=backend /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/backend/.venv/bin/python modules/memory/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module memory --check` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/memory/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module memory --check
```

## Boundaries

- Keep module business code and data inside `modules/memory/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
