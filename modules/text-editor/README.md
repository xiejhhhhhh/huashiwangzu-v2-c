# text-editor — 文本编辑器

## Responsibility

文本编辑器

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"text-editor"` |
| name | `"文本编辑器"` |
| category | `"file-editor"` |
| module_type | `"editor"` |
| module_family | `"desktop"` |
| product_status | `"active"` |
| window_type | `"normal"` |
| singleton | `false` |
| allow_multiple | `true` |
| show_in_launcher | `true` |
| show_on_desktop | `false` |
| route_prefix | `null` |
| contract_version | `"2.0"` |
| module_version | `"1.0.0"` |
| backend.enabled | `false` |
| backend.router | `null` |
| actual backend prefix | `N/A` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `N/A`

| Family | Methods | Purpose |
|---|---|---|
| N/A | N/A | No backend HTTP router |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 0

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| N/A | N/A | N/A | No public backend capability |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `text_editor_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

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
| `backend/router.py` | not present |
| `sandbox/test_module.py` | not present |
| `sandbox/package.json` | present |

## Acceptance

<!-- DOCS-SYNC: section=sandbox -->
| Area | Status | Verification |
|---|---|---|
| README | PASS | `modules/text-editor/README.md` |
| Acceptance matrix | PASS | present |
| Backend sandbox | SKIP | `N/A` |
| Frontend sandbox | PASS | `cd modules/text-editor/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module text-editor --check` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
# No backend sandbox test for this module
cd modules/text-editor/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module text-editor --check
```

## Boundaries

- Keep module business code and data inside `modules/text-editor/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
