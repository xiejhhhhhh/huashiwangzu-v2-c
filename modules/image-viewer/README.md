# image-viewer — Image viewer for common image formats

## Responsibility
Opens and renders image files (png, jpg, jpeg, gif, bmp, webp, svg, ico) in the desktop shell. Pure frontend viewer — no backend, no cross-module capabilities.

## Public capabilities
None. Passive file viewer only.

## HTTP endpoints
None. No `route_prefix` and no backend router.

## Data tables
None.

## How to query/use
The desktop shell opens this viewer automatically when a user double-clicks a matching image file (highest `sort_order: 10` among file-viewers). Other modules cannot invoke it.

## Boundaries/notes
- Frontend-only module; no backend or runtime.
- Default window 900×650, supports multiple instances.
- SVG is supported for viewing (not editing).

## Sandbox verification

```bash
cd modules/image-viewer/sandbox
npm install
npm run build

cd ../../../frontend
npm run build

cd ..
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --check
```

Expected result: `image-viewer` passes through its sandbox frontend build. There is no `sandbox/test_module.py` because this module has no backend router, no samples, and no cross-module capability.

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `image-viewer`, window `normal`, formats: png, jpg, jpeg, gif, bmp, webp, svg, ico. |
| Backend capability | SKIP | No backend capability; passive frontend module. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Uses framework file preview/open dispatch; no direct cross-module table access. |
| Sandbox | PASS | `cd modules/image-viewer/sandbox && npm run build` |
| Smoke | PASS | `npm --prefix frontend run build` plus desktop open-dispatch/browser test when UI is in scope. |
| Known debt | DEBT | Pure frontend viewer/editor; UI coverage depends on Playwright desktop-open tests. |

### Reproducible Checks

```bash
cd modules/image-viewer/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module image-viewer --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
