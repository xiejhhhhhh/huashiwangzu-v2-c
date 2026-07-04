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
| `pdf-parser` | `parse` | `{"file_id": int}` | Content IR-compatible document blocks |

## Dependencies

- `pdfplumber` (in backend venv)

## Format Support

- `.pdf` — Text extraction, table extraction, embedded image detection

## Content IR Contract

- `schema_version`: `content-ir/v1`
- `content_type`: `document`
- Top-level source fields: `source`, `source_file_id`, `source_module`, `parser`
- Block types: `heading`, `paragraph`, `table`, `image`
- Resources: detected images with `resource_type`, `mime_type`, optional `data_b64`, and `source_ref`
- Source trace: page number on every block/resource `source_ref`; image resources also include xref/name when available

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
| Content IR | PASS | Parser returns `schema_version`, source metadata, non-empty sample blocks, and page-level `source_ref`; sandbox normalizes through existing Content IR normalizer. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/pdf-parser/sandbox/test_module.py
cd modules/pdf-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module pdf-parser --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
