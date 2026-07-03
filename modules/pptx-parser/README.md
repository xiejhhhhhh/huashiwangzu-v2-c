# PPTX Parser Module

Parse PPTX files into unified content blocks (slide text, picture detection).

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pptx-parser/health` | GET | Module health check (public, no auth) |
| `/api/pptx-parser/parse` | POST | Parse PPTX file by `file_id` |

## Capability

| Module | Action | Input | Output |
|--------|--------|-------|--------|
| `pptx-parser` | `parse` | `{"file_id": int}` | Unified content block skeleton |

## Dependencies

- `python-pptx` (in backend venv)

## Format Support

- `.pptx` — Slide text, picture detection

## Verification

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/pptx-parser/sandbox/test_module.py
(cd modules/pptx-parser/sandbox && npm run build)

curl http://127.0.0.1:33000/api/pptx-parser/health
python3.14 scripts/check-capability-drift.py
```
