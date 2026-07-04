# DOCX Parser Module

Parse DOCX files into unified content blocks (paragraphs, tables, inline images).

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/docx-parser/health` | GET | Module health check (public, no auth) |
| `/api/docx-parser/parse` | POST | Parse DOCX file by `file_id` |

## Capability

| Module | Action | Input | Output |
|--------|--------|-------|--------|
| `docx-parser` | `parse` | `{"file_id": int}` | Content IR-compatible document blocks |

The backend capability uses the framework uploaded-file runner, so `file_id`
access is validated through the platform file permission path before the module
reads the physical file. Parser exceptions propagate as failures; corrupt DOCX
files are not wrapped as successful parse results.

## Dependencies

- `python-docx` (in backend venv)

## Format Support

- `.docx` — Paragraphs, tables, inline images

## Content IR Contract

- `schema_version`: `content-ir/v1`
- `content_type`: `document`
- Top-level source fields: `source`, `source_file_id`, `source_module`, `parser`
- Block types: `heading`, `paragraph`, `table`, `image`
- Resources: inline images with `resource_type`, `mime_type`, `data_b64`, and `source_ref`
- Source trace: paragraph/table/resource positions in `source_ref`; DOCX pages are not available from `python-docx`, so legacy `page` remains `null`

## Verification

```bash
# Module lint
cd /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2
backend/.venv/bin/ruff check modules/docx-parser/backend/router.py modules/docx-parser/backend/parser.py modules/docx-parser/sandbox/test_module.py

# Sandbox parser contract test with real sample + generated boundary fixtures
PYTHONPATH=backend backend/.venv/bin/python modules/docx-parser/sandbox/test_module.py

# Sandbox frontend build
cd modules/docx-parser/sandbox && npm run build

# Health check
curl http://127.0.0.1:33000/api/docx-parser/health

# Parse a file
curl -X POST http://127.0.0.1:33000/api/docx-parser/parse \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"file_id": <id>}'
```

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `docx-parser`, window `normal`, formats: Not format-bound. |
| Backend capability | PASS | 1 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Parses by file_id through framework/parser access checks; verify with sandbox sample. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/docx-parser/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `docx-parser:<action>` and release smoke/capability drift gates. |
| Content IR | PASS | Parser returns `schema_version`, source metadata, non-empty sample blocks, and block/resource `source_ref`; sandbox normalizes through existing Content IR normalizer. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/docx-parser/sandbox/test_module.py
cd modules/docx-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module docx-parser --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
