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
