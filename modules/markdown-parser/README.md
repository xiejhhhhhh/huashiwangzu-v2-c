# markdown-parser

## Responsibility

`markdown-parser` is a parser service in the V2 desktop/module architecture. It is declared by `manifest.json` and must be consumed through the framework runtime, HTTP router, or capability registry rather than direct cross-module imports.

## Public Capabilities

| Capability | min_role | Notes |
|---|---|---|
| `markdown-parser:parse` | viewer | Parse Markdown files into unified content blocks with heading levels |

## Boundaries

- Business logic stays inside this module directory.
- Cross-module access must go through the framework capability registry or runtime SDK.
- Framework file content access must preserve `check_file_access` semantics when `file_id` is used.

## Content IR Compatibility

The parser keeps the legacy `{file_id, format, blocks, resources}` shape and adds Content IR
compatible fields: `schema_version`, `content_type`, `source`, `source_file_id`, `source_module`,
`parser`, `metadata`, and `warnings`. Blocks include `source_ref` with file id, format, section, and
line bounds where Markdown exposes them. Image resources also carry `source_ref`, and empty successful
parses emit an explicit paragraph block so the existing Content IR normalizer can produce block ids.

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `markdown-parser`, window `background-service`, formats: Not format-bound. |
| Backend capability | PASS | 1 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Background service is intentionally hidden from launcher with empty component_key. |
| File access | PASS | Parses by file_id through framework/parser access checks; verify with sandbox sample. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/markdown-parser/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `markdown-parser:<action>` and release smoke/capability drift gates. |
| Content IR | PASS | Sandbox normalizes parser output with existing `normalize_ir` and checks `schema_version`, non-empty blocks/resources shape, and `source_ref`. |
| Known debt | PASS | No module-local Content IR debt found for Markdown parsing. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/markdown-parser/sandbox/test_module.py
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module markdown-parser --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
