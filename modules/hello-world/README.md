# Hello World Module

Sample module for scaffolding and integration testing.

## Capability

No HTTP API or capability registered. Used as a minimal verification target in framework tests.

## Verification

```bash
cd modules/hello-world/sandbox
npm install
npm run build

cd ../../../frontend
npm run build

cd ..
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --check
```

Expected result: `hello-world` passes through its sandbox frontend build and remains registered in the main frontend build. There is no `sandbox/test_module.py` because this sample has no backend router, samples, data tables, or cross-module capability.

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `hello-world`, window `normal`, formats: Not format-bound. |
| Backend capability | SKIP | No backend capability; passive frontend module. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | SKIP | Module does not directly consume framework file_id content. |
| Sandbox | PASS | `cd modules/hello-world/sandbox && npm run build` |
| Smoke | PASS | `npm --prefix frontend run build` plus desktop open-dispatch/browser test when UI is in scope. |
| Known debt | PASS | None tracked in this matrix. |

### Reproducible Checks

```bash
cd modules/hello-world/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module hello-world --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
