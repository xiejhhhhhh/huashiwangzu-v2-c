# im — 消息

## Responsibility

消息

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"im"` |
| name | `"消息"` |
| category | `"tools"` |
| window_type | `"normal"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `true` |
| show_on_desktop | `false` |
| route_prefix | `"/api/im"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/im` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/im`

| Family | Methods | Purpose |
|---|---|---|
| `conversations` | GET/POST | Endpoint family under `/api/im` |
| `messages` | POST | Endpoint family under `/api/im` |
| `unread-count` | GET | Endpoint family under `/api/im` |
| `users` | GET | Endpoint family under `/api/im` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 2

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `notify` | `editor` | `content`, `title`, `user_id` | 向用户发送站内通知 |
| `send` | `viewer` | `content`, `conversation_id` | 向现有 IM 对话发送消息 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `im_conversations` | Owned by `im` module |
| `im_messages` | Owned by `im` module |
| `im_read_state` | Owned by `im` module |

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
| Manifest contract | PASS | `modules/im/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="im", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/im/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module im --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/im/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module im --check
```

## Boundaries

- Keep module business code and data inside `modules/im/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
