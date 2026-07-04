# PDF Parser Module

Parse PDF files into unified content blocks via pdfplumber.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pdf-parser/health` | GET | Module health check (public, no auth) |
| `/api/pdf-parser/parse` | POST | Parse PDF file by `file_id` |

## Capability

| Module | Action | Input | Output |
|--------|--------|-------|--------|
| `pdf-parser` | `parse` | `{"file_id": int}` | Unified content block skeleton |

## Dependencies

- `pdfplumber` (in backend venv)

## Format Support

- `.pdf` — Text extraction, table extraction, embedded image detection

## Verification

```bash
# Sandbox parser test with the backend runtime dependencies
cd modules/pdf-parser/sandbox
../../../backend/.venv/bin/python test_module.py
../../../backend/.venv/bin/python -m pytest test_module.py

# Sandbox frontend build
npm run build

# Health check
curl http://127.0.0.1:33000/api/pdf-parser/health

# Parse a file
curl -X POST http://127.0.0.1:33000/api/pdf-parser/parse \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"file_id": <id>}'
```

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `pdf-parser`, window `normal`, formats: Not format-bound. |
| Backend capability | PASS | 1 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Parses by file_id through framework/parser access checks; verify with sandbox sample. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/pdf-parser/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `pdf-parser:<action>` and release smoke/capability drift gates. |
| Known debt | DEBT | Keep real sample coverage and Content IR compatibility in parser sandbox. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/pdf-parser/sandbox/test_module.py
cd modules/pdf-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module pdf-parser --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
