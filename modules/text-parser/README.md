# Text/Markdown Parser Module

Parse TXT and Markdown files into unified content blocks.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/text-parser/health` | GET | Module health check (public, no auth) |
| `/api/text-parser/parse` | POST | Parse text/markdown file by `file_id` |

## Capability

| Module | Action | Input | Output |
|--------|--------|-------|--------|
| `text-parser` | `parse` | `{"file_id": int}` | Unified content block skeleton |

The backend capability resolves `file_id` through the shared uploaded-file runner, which enforces
`check_file_access(db, file_id, user_id)` before reading file bytes from disk.

## Dependencies

- No third-party libraries. Pure standard library.

## Format Support

- `.txt`, `.text`, `.log` — Paragraph-grouped plain text
- `.md`, `.markdown` — Heading-aware, code block-aware, paragraph grouping

Large text files are parsed up to `MAX_TEXT_BYTES` plus a small multibyte safety margin. The response
includes `metadata.original_size`, `metadata.parsed_bytes`, `metadata.max_bytes`,
`metadata.truncated`, and `metadata.encoding`.

## Verification

```bash
# Static check
cd /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2
backend/.venv/bin/ruff check modules/text-parser/backend/router.py modules/text-parser/backend/parser.py modules/text-parser/sandbox/test_module.py

# Sandbox parser tests with real samples and boundary cases
backend/.venv/bin/python -m pytest modules/text-parser/sandbox/test_module.py

# Sandbox frontend build
cd /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/text-parser/sandbox
npm run build

# Health check against the live backend
curl http://127.0.0.1:33000/api/text-parser/health

# Parse a file against the live backend
curl -X POST http://127.0.0.1:33000/api/text-parser/parse \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"file_id": <id>}'
```

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `text-parser`, window `normal`, formats: Not format-bound. |
| Backend capability | PASS | 1 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Parses by file_id through framework/parser access checks; verify with sandbox sample. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/text-parser/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `text-parser:<action>` and release smoke/capability drift gates. |
| Known debt | DEBT | Keep real sample coverage and Content IR compatibility in parser sandbox. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/text-parser/sandbox/test_module.py
cd modules/text-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module text-parser --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
