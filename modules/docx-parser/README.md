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
| `docx-parser` | `parse` | `{"file_id": int}` | Unified content block skeleton |

The backend capability uses the framework uploaded-file runner, so `file_id`
access is validated through the platform file permission path before the module
reads the physical file. Parser exceptions propagate as failures; corrupt DOCX
files are not wrapped as successful parse results.

## Dependencies

- `python-docx` (in backend venv)

## Format Support

- `.docx` — Paragraphs, tables, inline images

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
