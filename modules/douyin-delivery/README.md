# douyin-delivery — 抖音内容与计划助手

## Responsibility

Douyin delivery module for scripts, ad copy, content validation, delivery task handoff, and cleanup.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"douyin-delivery"` |
| name | `"抖音内容与计划助手"` |
| category | `"AI"` |
| window_type | `"normal"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `true` |
| show_on_desktop | `true` |
| route_prefix | `"/api/douyin-delivery"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/douyin-delivery` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/douyin-delivery`

| Family | Methods | Purpose |
|---|---|---|
| `accounts` | DELETE/GET/POST/PUT | Endpoint family under `/api/douyin-delivery` |
| `ad-copies` | DELETE/GET/POST/PUT | Endpoint family under `/api/douyin-delivery` |
| `campaigns` | DELETE/GET/POST/PUT | Endpoint family under `/api/douyin-delivery` |
| `cleanup` | POST | Endpoint family under `/api/douyin-delivery` |
| `delivery-tasks` | DELETE/GET/POST/PUT | Endpoint family under `/api/douyin-delivery` |
| `materials` | DELETE/GET/POST/PUT | Endpoint family under `/api/douyin-delivery` |
| `products` | DELETE/GET/POST/PUT | Endpoint family under `/api/douyin-delivery` |
| `prompts` | DELETE/GET/POST | Endpoint family under `/api/douyin-delivery` |
| `scripts` | DELETE/GET/POST/PUT | Endpoint family under `/api/douyin-delivery` |
| `validate` | POST | Endpoint family under `/api/douyin-delivery` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 6

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `cleanup_marked_data` | `editor` | `marker` | 按 marker 清理当前用户测试数据（含投递任务 payload/result_payload） |
| `create_delivery_task` | `editor` | `auto_execute`, `payload`, `target_id`, `target_type`, `task_type` | 创建内容交接任务并同步推进可审计状态；不调用外部广告平台 |
| `generate_ad_copy` | `editor` | `ad_type`, `channel`, `product` | 生成广告文案 |
| `generate_script` | `editor` | `channel`, `product` | 生成抖音口播脚本 |
| `mark_task_failed` | `editor` | `error_message`, `result_payload`, `task_id` | 把交接任务标记为 failed 并写入失败原因 |
| `validate_content` | `editor` | `content` | 知识库校验成分/功效内容 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `douyin_accounts` | Owned by `douyin-delivery` module |
| `douyin_ad_copies` | Owned by `douyin-delivery` module |
| `douyin_campaigns` | Owned by `douyin-delivery` module |
| `douyin_delivery_tasks` | Owned by `douyin-delivery` module |
| `douyin_materials` | Owned by `douyin-delivery` module |
| `douyin_products` | Owned by `douyin-delivery` module |
| `douyin_prompts` | Owned by `douyin-delivery` module |
| `douyin_scripts` | Owned by `douyin-delivery` module |

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
| Manifest contract | PASS | `modules/douyin-delivery/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="douyin-delivery", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/douyin-delivery/sandbox/test_module.py` |
| Frontend sandbox | PASS | `cd modules/douyin-delivery/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module douyin-delivery --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/douyin-delivery/sandbox/test_module.py
cd modules/douyin-delivery/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module douyin-delivery --check
```

## Boundaries

- Keep module business code and data inside `modules/douyin-delivery/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
