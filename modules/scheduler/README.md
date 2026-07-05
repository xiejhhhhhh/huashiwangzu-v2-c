# scheduler — 定时任务

## Responsibility

定时任务

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"scheduler"` |
| name | `"定时任务"` |
| category | `"tools"` |
| module_type | `"service"` |
| module_family | `"agent"` |
| product_status | `"background"` |
| window_type | `"normal"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/scheduler"` |
| contract_version | `"2.0"` |
| module_version | `"1.0.0"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/scheduler` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/scheduler`

| Family | Methods | Purpose |
|---|---|---|
| `cancel` | POST | Endpoint family under `/api/scheduler` |
| `create` | POST | Endpoint family under `/api/scheduler` |
| `list` | GET | Endpoint family under `/api/scheduler` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 3

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `cancel` | `editor` | `task_id` | 取消自己创建的定时任务 |
| `create` | `editor` | `action_description`, `recur`, `scheduled_at`, `title` | 创建定时任务：传入标题、时间/周期、动作描述，到期自动执行并推送结果到本人 IM |
| `list` | `viewer` | none | 列出自己创建的定时任务 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `scheduler_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

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
| README | PASS | `modules/scheduler/README.md` |
| Acceptance matrix | PASS | present |
| Backend sandbox | PASS | `PYTHONPATH=backend /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/backend/.venv/bin/python modules/scheduler/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module scheduler --check` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/scheduler/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module scheduler --check
```

## Boundaries

- Keep module business code and data inside `modules/scheduler/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
