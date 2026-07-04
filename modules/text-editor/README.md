# text-editor — Plain text and code editor

## Responsibility
Opens and edits plain text files: txt, md, log, json, csv, yaml, yml, xml, ini, cfg. Most formats are editable (except csv is view-only). Pure frontend module — no backend, no cross-module capabilities.

## Public capabilities
None. Passive file editor only.

## HTTP endpoints
None. No `route_prefix` and no backend router.

## Data tables
None.

## How to query/use
The desktop shell opens this editor when a user double-clicks or selects "Edit" on a matching text file. Uses `sort_order: 20` for file-open scheduling (after image-viewer 10).

## Boundaries/notes
- Frontend-only module; no backend or runtime.
- `editable_formats` excludes csv (view-only), all others are editable.
- Supports 10 text/code formats.
- Default window 900×650, supports multiple instances.

## Sandbox verification

```bash
cd modules/text-editor/sandbox
npm install
npm run build

cd ../../../frontend
npm run build

cd ..
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --check
```

Expected result: `text-editor` passes through its sandbox frontend build. There is no `sandbox/test_module.py` because this module has no backend router, no samples, and no cross-module capability.

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `text-editor`, window `normal`, formats: txt, md, log, json, csv, yaml, yml, xml, ini, cfg. |
| Backend capability | SKIP | No backend capability; passive frontend module. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Uses framework file preview/open dispatch; no direct cross-module table access. |
| Sandbox | PASS | `cd modules/text-editor/sandbox && npm run build` |
| Smoke | PASS | `npm --prefix frontend run build` plus desktop open-dispatch/browser test when UI is in scope. |
| Known debt | DEBT | Pure frontend viewer/editor; UI coverage depends on Playwright desktop-open tests. |

### Reproducible Checks

```bash
cd modules/text-editor/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module text-editor --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
