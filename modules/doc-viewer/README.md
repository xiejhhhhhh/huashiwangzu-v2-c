# doc-viewer — 文档查看器

## Responsibility

文档查看器

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"doc-viewer"` |
| name | `"文档查看器"` |
| category | `"file-viewer"` |
| window_type | `"normal"` |
| singleton | `false` |
| allow_multiple | `true` |
| show_in_launcher | `true` |
| show_on_desktop | `false` |
| route_prefix | `None` |
| backend.enabled | `false` |
| backend.router | `None` |
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
| N/A | N/A | none | No public backend capability |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `doc_viewer_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

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
| Manifest contract | PASS | `modules/doc-viewer/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="doc-viewer", include_parameters=true)` |
| Backend sandbox | SKIP | `N/A` |
| Frontend sandbox | PASS | `cd modules/doc-viewer/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module doc-viewer --check` |
| Known debt | DEBT | UI-only module; backend sandbox test not applicable. |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
# No backend sandbox test for this module
cd modules/doc-viewer/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module doc-viewer --check
```

## Boundaries

- Keep module business code and data inside `modules/doc-viewer/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
