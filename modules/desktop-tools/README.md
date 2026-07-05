# desktop-tools — Desktop Tools

## Responsibility

Desktop Tools

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"desktop-tools"` |
| name | `"Desktop Tools"` |
| category | `"tools"` |
| module_type | `"service"` |
| module_family | `"desktop"` |
| product_status | `"core"` |
| window_type | `"background-service"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/desktop-tools"` |
| contract_version | `"2.0"` |
| module_version | `"1.0.0"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/desktop-tools` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/desktop-tools`

| Family | Methods | Purpose |
|---|---|---|
| `health` | GET | Endpoint family under `/api/desktop-tools` |
| `list-apps` | GET | Endpoint family under `/api/desktop-tools` |
| `list-files` | POST | Endpoint family under `/api/desktop-tools` |
| `read-file` | POST | Endpoint family under `/api/desktop-tools` |
| `search-files` | POST | Endpoint family under `/api/desktop-tools` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 15

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `copy_file` | `editor` | `file_id`, `target_folder_id` | Copy a file. |
| `create_file` | `editor` | `content`, `extension`, `folder_id`, `name` | Create a new file with text content. |
| `delete_file` | `editor` | `file_id` | Soft-delete a file. |
| `get_file` | `viewer` | `file_id` | Get a single file's metadata by file_id. |
| `list_apps` | `viewer` | object | List desktop applications available to the current user. |
| `list_files` | `viewer` | `folder_id`, `page`, `page_size` | List files in a folder (or root). Returns file name, type, size, and id. |
| `list_versions` | `viewer` | `artifact_id` | List file versions (via artifact). |
| `publish_artifact` | `editor` | `artifact_id`, `target_file_id` | Publish an artifact to the desktop as a file. |
| `read_file` | `viewer` | `file_id` | Read file content by file_id. Routes to format parsers (PDF, DOCX, XLSX, etc.) and returns text content capped at 20000 chars with truncation metadata. |
| `refresh` | `viewer` | object | Trigger desktop file list refresh. |
| `rename_file` | `editor` | `file_id`, `new_name` | Rename a file. |
| `replace_file` | `editor` | `new_content`, `old_file_id`, `source_artifact_id`, `source_file_id` | Replace file content from text, artifact, or another file. No base64 needed. |
| `replace_file_from_artifact` | `editor` | `source_artifact_id`, `target_file_id` | Replace a desktop file using content from an artifact. No base64 needed. |
| `restore_version` | `editor` | `artifact_id`, `version_id` | Restore a file to a previous version. |
| `search_files` | `viewer` | `extension`, `keyword`, `page`, `page_size` | Search files by keyword and/or extension. Returns matching file metadata. |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `desktop_tools_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

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
| README | PASS | `modules/desktop-tools/README.md` |
| Acceptance matrix | PASS | present |
| Backend sandbox | PASS | `PYTHONPATH=backend /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/backend/.venv/bin/python modules/desktop-tools/sandbox/test_module.py` |
| Frontend sandbox | PASS | `cd modules/desktop-tools/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module desktop-tools --check` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/desktop-tools/sandbox/test_module.py
cd modules/desktop-tools/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module desktop-tools --check
```

## Boundaries

- Keep module business code and data inside `modules/desktop-tools/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
