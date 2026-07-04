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
| `pptx-parser` | `parse` | `{"file_id": int}` | Content IR-compatible presentation slide blocks |

## Dependencies

- `python-pptx` (in backend venv)

## Format Support

- `.pptx` — Slide text, picture detection

## Content IR Contract

- `schema_version`: `content-ir/v1`
- `content_type`: `presentation`
- Top-level source fields: `source`, `source_file_id`, `source_module`, `parser`
- Top-level block type: `slide`
- Nested block types: `heading`, `paragraph`, `image`
- Resources: slide images with `resource_type`, `mime_type`, `data_b64`, and `source_ref`
- Source trace: slide number on every slide block, nested block, and resource `source_ref`; nested blocks also include shape name when available

## Verification

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/pptx-parser/sandbox/test_module.py
(cd modules/pptx-parser/sandbox && npm run build)

curl http://127.0.0.1:33000/api/pptx-parser/health
python3.14 scripts/check-capability-drift.py
```

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `pptx-parser`, window `normal`, formats: Not format-bound. |
| Backend capability | PASS | 1 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Parses by file_id through framework/parser access checks; verify with sandbox sample. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/pptx-parser/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `pptx-parser:<action>` and release smoke/capability drift gates. |
| Content IR | PASS | Parser returns `schema_version`, presentation slide blocks, non-empty sample blocks, and slide-level `source_ref`; sandbox normalizes through existing Content IR normalizer. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/pptx-parser/sandbox/test_module.py
cd modules/pptx-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module pptx-parser --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
