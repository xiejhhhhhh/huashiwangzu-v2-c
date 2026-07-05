# docx-parser — DOCX Parser

## Responsibility

DOCX Parser

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"docx-parser"` |
| name | `"DOCX Parser"` |
| category | `"tools"` |
| module_type | `"parser"` |
| module_family | `"office"` |
| product_status | `"background"` |
| window_type | `"normal"` |
| singleton | `false` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/docx-parser"` |
| contract_version | `"2.0"` |
| module_version | `"1.0.0"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/docx-parser` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/docx-parser`

| Family | Methods | Purpose |
|---|---|---|
| `health` | GET | Endpoint family under `/api/docx-parser` |
| `parse` | POST | Endpoint family under `/api/docx-parser` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 1

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `parse` | `viewer` | `file_id` | Parse DOCX file into unified content blocks |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `docx_parser_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

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
| README | PASS | `modules/docx-parser/README.md` |
| Acceptance matrix | PASS | present |
| Backend sandbox | PASS | `PYTHONPATH=backend /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/backend/.venv/bin/python modules/docx-parser/sandbox/test_module.py` |
| Frontend sandbox | PASS | `cd modules/docx-parser/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module docx-parser --check` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/docx-parser/sandbox/test_module.py
cd modules/docx-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module docx-parser --check
```

## Boundaries

- Keep module business code and data inside `modules/docx-parser/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
