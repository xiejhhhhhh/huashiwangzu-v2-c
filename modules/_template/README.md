# Module Template

Copy this directory to create a new module. Keep this README structure in every new module so `docs_sync` can refresh generated facts.

## Quick Start

```bash
# 1. Copy the template
cp -r modules/_template modules/YOUR_MODULE_KEY

# 2. Replace placeholders, case-sensitive:
#    MODULE_KEY          -> your-module-key
#    MODULE_DISPLAY_NAME -> Your Module Display Name
#
#    Files to update:
#      README.md
#      manifest.json
#      frontend/index.vue
#      sandbox/package.json
#      sandbox/index.html
#      sandbox/src/App.vue

# 3. Pick a unique sandbox port if needed
#    export VITE_SANDBOX_PORT=5175 && npm run dev

# 4. Install and run the isolated sandbox
cd modules/YOUR_MODULE_KEY/sandbox
npm install
npm run dev
```

The template is frontend-only by default: `manifest.backend.enabled=false` and no `backend/` directory is present. If the module needs backend behavior, add module-local `backend/router.py`, schemas, service, models, capabilities, and sandbox tests; do not place business logic in `backend/app/`.

Set `module_type`, `module_family`, and `product_status` in `manifest.json` before handoff. These fields are logical taxonomy only: modules remain flat under `modules/{key}` and same-family modules still communicate through the capability bus.

## Responsibility

Describe what the module owns in one or two paragraphs. Keep history, task notes, and delivery logs out of the module README.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"MODULE_KEY"` |
| name | `"MODULE_DISPLAY_NAME"` |
| category | `"tools"` |
| module_type | `"app"` |
| module_family | `"desktop"` |
| product_status | `"active"` |
| component_key | `"index.vue"` |
| route_prefix | `null` |
| permissions | `["viewer", "editor", "admin"]` |
| backend.enabled | `false` |
| singleton | `false` |
| show_in_launcher | `true` |
| supported_formats | `[]` |
<!-- /DOCS-SYNC -->

## Current Capabilities

List current user-visible capabilities. Do not describe planned or historical capabilities as current facts.

## HTTP API / Endpoint Families

- Frontend-only modules: `N/A`.
- Backend modules: list module-local endpoint families and keep the exact route facts synchronized from code.

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 0

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| N/A | N/A | N/A | No public backend capability |
<!-- /DOCS-SYNC -->

## Data Ownership

- Own only tables prefixed by this module key when backend storage exists.
- Do not read/write another module's tables directly.
- Use `/api/modules/call` or `platform.modules.call` for cross-module interaction.

## Cross-Module Dependencies

List any cross-module calls here. If there are none, write `None`.

## File Access / Permission Boundary

- Any `file_id` read must pass framework file access checks before disk access.
- Module-generated files must stay under framework-managed file services or module-owned paths.
- Do not assume host desktop access from terminal or sandbox tools.

## Frontend / Backend Structure

```text
modules/MODULE_KEY/
  manifest.json
  README.md
  frontend/
    index.vue
  runtime/
    index.ts
  sandbox/
    package.json
    vite.config.ts
    src/App.vue
```

For backend-enabled modules, add:

```text
modules/MODULE_KEY/backend/
  router.py
  schemas.py
  service.py
  models.py
  capabilities.py
modules/MODULE_KEY/sandbox/test_module.py
```

## Acceptance

<!-- DOCS-SYNC: section=sandbox -->
| Area | Status | Verification |
|---|---|---|
| README | PASS | `modules/MODULE_KEY/README.md` |
| Acceptance matrix | DEBT | Run `docs_sync` and `module_sandbox_matrix` after module creation |
| Backend sandbox | SKIP | `N/A` |
| Frontend sandbox | PASS | `cd modules/MODULE_KEY/sandbox && npm run build` |
| Matrix check | PASS | `python3.14 dev_toolkit/module_sandbox_matrix.py --json` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
cd modules/MODULE_KEY/sandbox && npm run build
python3.14 dev_toolkit/capability_contract_diff.py --module MODULE_KEY --include-parameters
python3.14 dev_toolkit/module_sandbox_matrix.py --json
```

If the module has backend behavior, also run the module sandbox test and live probes/capability calls.

## Boundaries

- Module tasks may change only `modules/MODULE_KEY/` unless a separate framework task is explicitly assigned.
- Module UI must use module runtime/platform APIs, not private framework imports.
- Runtime `register_capability(...)` is authoritative; manifest `public_actions` must not drift.
- Keep the three `DOCS-SYNC` marker blocks in this README. `docs_sync` updates existing blocks; it does not infer where missing blocks belong.
