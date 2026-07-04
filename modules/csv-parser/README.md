# csv-parser

## Responsibility

`csv-parser` is a parser service in the V2 desktop/module architecture. It is declared by `manifest.json` and must be consumed through the framework runtime, HTTP router, or capability registry rather than direct cross-module imports.

## Public Capabilities

| Capability | min_role | Notes |
|---|---|---|
| `csv-parser:parse` | viewer | Parse CSV/TSV files into unified content blocks |

## Boundaries

- Business logic stays inside this module directory.
- Cross-module access must go through the framework capability registry or runtime SDK.
- Framework file content access must preserve `check_file_access` semantics when `file_id` is used.

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `csv-parser`, window `background-service`, formats: Not format-bound. |
| Backend capability | PASS | 1 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Background service is intentionally hidden from launcher with empty component_key. |
| File access | PASS | Parses by file_id through framework/parser access checks; verify with sandbox sample. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/csv-parser/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `csv-parser:<action>` and release smoke/capability drift gates. |
| Known debt | DEBT | Keep real sample coverage and Content IR compatibility in parser sandbox. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/csv-parser/sandbox/test_module.py
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module csv-parser --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
