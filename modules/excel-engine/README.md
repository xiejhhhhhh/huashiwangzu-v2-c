# excel-engine — Excel 编辑器

## Responsibility

Spreadsheet engine for parsing, workbook state, edits, history, versions, export, compile, and desktop publish.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"excel-engine"` |
| name | `"Excel 编辑器"` |
| category | `"file-editor"` |
| window_type | `"normal"` |
| singleton | `false` |
| allow_multiple | `true` |
| show_in_launcher | `true` |
| show_on_desktop | `false` |
| route_prefix | `None` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/excel-engine` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/excel-engine`

| Family | Methods | Purpose |
|---|---|---|
| `clipboard` | POST | Endpoint family under `/api/excel-engine` |
| `dispatch` | POST | Endpoint family under `/api/excel-engine` |
| `download` | GET | Endpoint family under `/api/excel-engine` |
| `edit` | POST | Endpoint family under `/api/excel-engine` |
| `export` | POST | Endpoint family under `/api/excel-engine` |
| `health` | GET | Endpoint family under `/api/excel-engine` |
| `open` | POST | Endpoint family under `/api/excel-engine` |
| `parse` | POST | Endpoint family under `/api/excel-engine` |
| `state` | POST | Endpoint family under `/api/excel-engine` |
| `style` | POST | Endpoint family under `/api/excel-engine` |
| `table` | POST | Endpoint family under `/api/excel-engine` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 13

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `append_rows` | `editor` | `rows`, `sheet`, `state_key` | Append rows to the end of a sheet |
| `compile_xlsx` | `viewer` | `sheet`, `state_key` | Compile workbook to temporary XLSX for download without creating a file record |
| `create_workbook` | `editor` | `name`, `state_key` | Create a new empty workbook in the database |
| `export_xlsx` | `editor` | `folder_id`, `sheet`, `state_key` | Export workbook to XLSX file |
| `import_file_to_workbook` | `editor` | `file_id`, `state_key` | Import a file into a database workbook for editing |
| `list_history` | `viewer` | `state_key` | List operation history for a workbook |
| `list_versions` | `viewer` | `state_key` | List saved versions of a workbook |
| `parse` | `viewer` | `file_id` | Parse XLSX/CSV files into cell data |
| `publish_to_desktop` | `editor` | `folder_id`, `sheet`, `state_key`, `target_file_id` | Publish workbook to desktop |
| `redo` | `editor` | `state_key` | Redo the last undone operation |
| `restore_version` | `editor` | `state_key`, `version_id` | Restore a workbook to a saved version |
| `undo` | `editor` | `state_key` | Undo the last operation |
| `update_range` | `editor` | `rows`, `sheet`, `start_col`, `start_row`, `state_key` | Update a range of cells |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `excel_cells` | Owned by `excel-engine` module |
| `excel_col_widths` | Owned by `excel-engine` module |
| `excel_history` | Owned by `excel-engine` module |
| `excel_redo_stack` | Owned by `excel-engine` module |
| `excel_row_heights` | Owned by `excel-engine` module |
| `excel_sheets` | Owned by `excel-engine` module |
| `excel_versions` | Owned by `excel-engine` module |
| `excel_workbooks` | Owned by `excel-engine` module |

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
| Manifest contract | PASS | `modules/excel-engine/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="excel-engine", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/excel-engine/sandbox/test_module.py` |
| Frontend sandbox | PASS | `cd modules/excel-engine/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module excel-engine --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/excel-engine/sandbox/test_module.py
cd modules/excel-engine/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module excel-engine --check
```

## Boundaries

- Keep module business code and data inside `modules/excel-engine/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
