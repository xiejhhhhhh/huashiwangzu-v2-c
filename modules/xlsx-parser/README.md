# XLSX Parser Module

Parse XLSX and CSV files into unified content blocks.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/xlsx-parser/health` | GET | Module health check (public, no auth) |
| `/api/xlsx-parser/parse` | POST | Parse XLSX/CSV file by `file_id` |

## Capability

| Module | Action | Input | Output |
|--------|--------|-------|--------|
| `xlsx-parser` | `parse` | `{"file_id": int}` | Unified content block skeleton |

## Dependencies

- `openpyxl` (in backend venv)
- Standard library `csv` for CSV parsing

## Format Support

- `.xlsx` — sheet-wise table blocks. Formula cells preserve the formula text when no cached value is present.
- `.csv` — CSV content as table blocks

Legacy `.xls` is not accepted by this module because the backend parser is based on `openpyxl`.
Unsupported extensions fail through the framework unified error response instead of returning an empty success.

## Parser Contract

- File access is enforced through the framework uploaded-file capability path before disk reads.
- Successful parses return `{file_id, format, blocks, resources}` plus optional `warnings` and `metadata`.
- Empty workbooks/CSVs are valid empty parses and include explicit warnings such as `empty_workbook`.
- Corrupt or unsupported files raise parser errors and are returned by the framework as `success:false`.
- XLSX and CSV row output is capped at 5000 emitted non-empty rows per sheet/file with a truncation marker.

## Verification

```bash
# Health check
curl http://127.0.0.1:33000/api/xlsx-parser/health

# Parse a file
curl -X POST http://127.0.0.1:33000/api/xlsx-parser/parse \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"file_id": <id>}'

# Sandbox parser regression test with real sample files
cd modules/xlsx-parser/sandbox
../../../backend/.venv/bin/python test_module.py
```

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `xlsx-parser`, window `normal`, formats: Not format-bound. |
| Backend capability | PASS | 1 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Parses by file_id through framework/parser access checks; verify with sandbox sample. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/xlsx-parser/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `xlsx-parser:<action>` and release smoke/capability drift gates. |
| Known debt | DEBT | Keep real sample coverage and Content IR compatibility in parser sandbox. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/xlsx-parser/sandbox/test_module.py
cd modules/xlsx-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module xlsx-parser --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
