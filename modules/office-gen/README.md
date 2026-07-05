# office-gen — Office Document Generator

## Responsibility

Office generation module for docx, xlsx, pptx, pdf, Content IR aliases, and artifact generation.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"office-gen"` |
| name | `"Office Document Generator"` |
| category | `"tools"` |
| window_type | `"normal"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `true` |
| show_on_desktop | `false` |
| route_prefix | `"/api/office-gen"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/office-gen` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/office-gen`

| Family | Methods | Purpose |
|---|---|---|
| `convert` | POST | Endpoint family under `/api/office-gen` |
| `docx` | POST | Endpoint family under `/api/office-gen` |
| `health` | GET | Endpoint family under `/api/office-gen` |
| `pdf` | POST | Endpoint family under `/api/office-gen` |
| `pptx` | POST | Endpoint family under `/api/office-gen` |
| `xlsx` | POST | Endpoint family under `/api/office-gen` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 8

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `convert` | `editor` | `file_id`, `target_format` | Convert an existing office file from one format to another (e.g. pptx→pdf, docx→pdf) using LibreOffice headless |
| `docx` | `editor` | `blocks`, `content`, `content_ir`, `filename`, `folder_id` | Generate a Word (.docx) document from structured JSON and save it to the file system |
| `export_to_artifact` | `editor` | `file_id` | Export an existing office file as an artifact for version management |
| `generate_to_artifact` | `editor` | `blocks`, `content`, `content_ir`, `filename`, `folder_id`, `format`, `sheets`, `slides` | Generate an office file and return as an artifact (no file-name conflict) |
| `pdf` | `editor` | `blocks`, `content`, `content_ir`, `filename`, `folder_id` | Generate a PDF document from structured JSON (same schema as docx) and save it to the file system |
| `pptx` | `editor` | `blocks`, `content_ir`, `filename`, `folder_id`, `slides` | Generate a PowerPoint (.pptx) presentation from structured JSON and save it to the file system |
| `replace_existing` | `editor` | `blocks`, `content`, `content_ir`, `filename`, `format`, `sheets`, `slides`, `target_file_id` | Generate an office file and replace an existing file entry |
| `xlsx` | `editor` | `blocks`, `content_ir`, `filename`, `folder_id`, `sheets` | Generate an Excel (.xlsx) spreadsheet from structured JSON and save it to the file system |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `office_gen_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

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
| Manifest contract | PASS | `modules/office-gen/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="office-gen", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/office-gen/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module office-gen --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/office-gen/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module office-gen --check
```

## Boundaries

- Keep module business code and data inside `modules/office-gen/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
