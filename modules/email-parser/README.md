# Email Parser Module

Parse EML and MSG email files into unified content blocks and attachment resources.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/email-parser/health` | GET | Module health check |
| `/api/email-parser/parse` | POST | Parse an email file by `file_id` |

## Capability

| Module | Action | Input | Output |
|--------|--------|-------|--------|
| `email-parser` | `parse` | `{"file_id": int}` | Unified email content blocks and resources |

The backend capability uses the framework uploaded-file runner, so `file_id`
access is validated through the platform file permission path before this
module reads the physical file. Parser failures are returned as structured
validation errors instead of successful empty parses.

## Format Support

- `.eml` - Headers, plaintext body, HTML fallback body, attachment metadata and bytes.
- `.msg` - Headers, body, and attachments when `extract-msg` is installed in the backend environment.

## Verification

```bash
# Module lint
cd /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2
backend/.venv/bin/ruff check modules/email-parser/backend/router.py modules/email-parser/backend/parser.py modules/email-parser/sandbox/test_module.py

# Sandbox parser contract test with real sample + generated boundary fixtures
backend/.venv/bin/python modules/email-parser/sandbox/test_module.py
backend/.venv/bin/python -m pytest modules/email-parser/sandbox/test_module.py

# Health check
curl http://127.0.0.1:33000/api/email-parser/health

# Parse a file
curl -X POST http://127.0.0.1:33000/api/email-parser/parse \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"file_id": <id>}'
```
