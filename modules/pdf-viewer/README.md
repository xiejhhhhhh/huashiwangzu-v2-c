# pdf-viewer — PDF file viewer

## Responsibility
Opens and renders PDF files in the desktop shell using PDF.js. Pure frontend viewer — no backend, no cross-module capabilities.

## Public capabilities
None. Passive file viewer only.

## HTTP endpoints
None. No `route_prefix` and no backend router.

## Data tables
None.

## How to query/use
The desktop shell opens this viewer automatically when a user double-clicks a `.pdf` file (matching `supported_formats`). Uses `sort_order: 30` for file-open scheduling.

## Boundaries/notes
- Frontend-only module; no backend or runtime.
- Relies on the framework's file preview API for fetching PDF content.
- Window default size 950×700, supports multiple instances.

## Sandbox verification

```bash
cd modules/pdf-viewer/sandbox
npm install
npm run build

cd ../../../frontend
npm run build

cd ..
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --check
```

Expected result: `pdf-viewer` passes through its sandbox frontend build. There is no `sandbox/test_module.py` because this module has no backend router, no samples, and no cross-module capability.

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `pdf-viewer`, window `normal`, formats: pdf. |
| Backend capability | SKIP | No backend capability; passive frontend module. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Uses framework file preview/open dispatch; no direct cross-module table access. |
| Sandbox | PASS | `cd modules/pdf-viewer/sandbox && npm run build` |
| Smoke | PASS | `npm --prefix frontend run build` plus desktop open-dispatch/browser test when UI is in scope. |
| Known debt | DEBT | Pure frontend viewer/editor; UI coverage depends on Playwright desktop-open tests. |

### Reproducible Checks

```bash
cd modules/pdf-viewer/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module pdf-viewer --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
