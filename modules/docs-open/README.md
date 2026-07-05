# docs-open — 文档开放接口

## Responsibility

文档开放接口

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"docs-open"` |
| name | `"文档开放接口"` |
| category | `"tools"` |
| module_type | `"app"` |
| module_family | `"office"` |
| product_status | `"active"` |
| window_type | `"normal"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `true` |
| show_on_desktop | `false` |
| route_prefix | `"/api/docs"` |
| contract_version | `"2.0"` |
| module_version | `"1.0.0"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/docs` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/docs`

| Family | Methods | Purpose |
|---|---|---|
| `` | POST | Endpoint family under `/api/docs` |
| `embed` | GET | Endpoint family under `/api/docs` |
| `open` | POST | Endpoint family under `/api/docs` |
| `token` | POST | Endpoint family under `/api/docs` |
| `{file_id}` | GET/POST | Endpoint family under `/api/docs` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 3

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `create_doc` | `editor` | `title`, `type` | Create a new empty document |
| `get_content` | `viewer` | `file_id` | Get structured JSON content of a document |
| `open` | `viewer` | `file_id`, `mode` | Open a document by file_id, returns embed_url and content info |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `docs_open_token` | Owned by `docs-open` module |

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
| README | PASS | `modules/docs-open/README.md` |
| Acceptance matrix | PASS | present |
| Backend sandbox | PASS | `PYTHONPATH=backend /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/backend/.venv/bin/python modules/docs-open/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module docs-open --check` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/docs-open/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module docs-open --check
```

## Boundaries

- Keep module business code and data inside `modules/docs-open/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
