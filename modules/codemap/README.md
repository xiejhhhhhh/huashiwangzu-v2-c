# codemap — 代码地图

## Responsibility

Code map module for repository impact lookup, boundary checks, locks, search, metrics, and inaccuracy feedback.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"codemap"` |
| name | `"代码地图"` |
| category | `"tools"` |
| window_type | `"background-service"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/codemap"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/codemap` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/codemap`

| Family | Methods | Purpose |
|---|---|---|
| `check-boundary` | POST | Endpoint family under `/api/codemap` |
| `get-file` | POST | Endpoint family under `/api/codemap` |
| `health` | GET | Endpoint family under `/api/codemap` |
| `impact` | POST | Endpoint family under `/api/codemap` |
| `module-map` | POST | Endpoint family under `/api/codemap` |
| `rebuild` | POST | Endpoint family under `/api/codemap` |
| `search` | POST | Endpoint family under `/api/codemap` |
| `stats` | GET | Endpoint family under `/api/codemap` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 13

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `acquire_lock` | `viewer` | `agent_id`, `path`, `ttl` | 获取文件锁 |
| `check_boundary` | `viewer` | `module_key`, `path` | 检查文件或模块的边界合规性，返回违反隔离铁律的引用清单。 |
| `check_lock` | `viewer` | `path` | 检查文件锁状态 |
| `get_file` | `viewer` | `path` | 查询文件的代码地图信息：所属层/模块、语言、符号清单、依赖与被依赖、注册/调用的能力、涉及的表。 |
| `impact` | `viewer` | `path`, `symbol` | 查询影响面：正向（我依赖谁）+ 反向（谁依赖我）的传递闭包，返回波及的文件、模块、跨模块能力清单和风险等级。 |
| `list_feedback` | `admin` | `page`, `page_size`, `path` | 列出 codemap 反馈记录 |
| `list_locks` | `viewer` | none | 列出所有活跃文件锁 |
| `module_map` | `viewer` | `module_key` | 查询模块的对外能力、依赖的外部能力、边界健康状态。 |
| `rebuild` | `admin` | none | 全量重建代码索引 |
| `release_lock` | `viewer` | `path` | 释放文件锁 |
| `report_inaccuracy` | `viewer` | `actual`, `agent_id`, `codemap_said`, `path`, `query_type`, `reason` | 报告 codemap 查询结果与实际不符。Agent 实读验证后发现不准时调用。 |
| `search` | `viewer` | `keyword` | 按关键词模糊搜索文件和符号。 |
| `stats` | `viewer` | none | 返回索引规模、构建耗时、最后更新时间、解析 confidence、反馈样本数与 empirical_accuracy 状态。 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `codemap_feedback` | Owned by `codemap` module |

Use `db_schema()` for live database details. This module must not directly read or write other modules' tables.

## Cross-Module Dependencies

- Manifest dependencies are declared in `manifest.json` when needed.
- Runtime calls to other modules must use framework capability calls, not imports or direct DB reads.

## File Access / Permission Boundary

If this module consumes `file_id`, it must validate file access through framework file access helpers or an approved public capability before reading disk.

## Frontend / Backend Structure

| Path | Status |
|---|---|
| `frontend/index.vue` | not present |
| `runtime/index.ts` | present |
| `backend/router.py` | present |
| `sandbox/test_module.py` | present |
| `sandbox/package.json` | not present |

## Acceptance

<!-- DOCS-SYNC: section=sandbox -->
| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `modules/codemap/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="codemap", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/codemap/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module codemap --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/codemap/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module codemap --check
```

## Boundaries

- Keep module business code and data inside `modules/codemap/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
