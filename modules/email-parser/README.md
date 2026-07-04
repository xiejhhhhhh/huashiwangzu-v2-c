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

## Content IR Compatibility

The parser keeps the legacy `{file_id, format, blocks, resources, resource_diagnostics}` shape and
adds Content IR compatible fields: `schema_version`, `content_type`, `source`, `source_file_id`,
`source_module`, `parser`, `metadata`, and `warnings`. Blocks include `source_ref` with email
sections (`header`, `body`, `attachment`) and message-part metadata. Attachment resources also carry
`source_ref` with `attachment_index` and filename so Artifact, Knowledge, and Agent evidence can trace
the extracted resource back to the email part.

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

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `email-parser`, window `background-service`, formats: Not format-bound. |
| Backend capability | PASS | 1 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Background service is intentionally hidden from launcher with empty component_key. |
| File access | PASS | Parses by file_id through framework/parser access checks; verify with sandbox sample. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/email-parser/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `email-parser:<action>` and release smoke/capability drift gates. |
| Content IR | PASS | Sandbox normalizes parser output with existing `normalize_ir` and checks `schema_version`, non-empty blocks, attachment resources, and message-part `source_ref`. |
| Known debt | PASS | No module-local Content IR debt found for EML/MSG parsing. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/email-parser/sandbox/test_module.py
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module email-parser --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
