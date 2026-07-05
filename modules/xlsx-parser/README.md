# xlsx-parser — XLSX/CSV Parser

## Responsibility

XLSX/CSV Parser

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"xlsx-parser"` |
| name | `"XLSX/CSV Parser"` |
| category | `"tools"` |
| window_type | `"normal"` |
| singleton | `false` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/xlsx-parser"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/xlsx-parser` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/xlsx-parser`

| Family | Methods | Purpose |
|---|---|---|
| `health` | GET | Endpoint family under `/api/xlsx-parser` |
| `parse` | POST | Endpoint family under `/api/xlsx-parser` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 1

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `parse` | `viewer` | `file_id` | Parse XLSX/CSV files into unified content blocks |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `xlsx_parser_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

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
| Manifest contract | PASS | `modules/xlsx-parser/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="xlsx-parser", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/xlsx-parser/sandbox/test_module.py` |
| Frontend sandbox | PASS | `cd modules/xlsx-parser/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module xlsx-parser --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/xlsx-parser/sandbox/test_module.py
cd modules/xlsx-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module xlsx-parser --check
```

## Boundaries

- Keep module business code and data inside `modules/xlsx-parser/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
