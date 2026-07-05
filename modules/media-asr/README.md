# media-asr — Media ASR (Audio/Video to Text)

## Responsibility

Media ASR (Audio/Video to Text)

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"media-asr"` |
| name | `"Media ASR (Audio/Video to Text)"` |
| category | `"tools"` |
| module_type | `"provider"` |
| module_family | `"media"` |
| product_status | `"background"` |
| window_type | `"normal"` |
| singleton | `false` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/media-asr"` |
| contract_version | `"2.0"` |
| module_version | `"1.0.0"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/media-asr` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/media-asr`

| Family | Methods | Purpose |
|---|---|---|
| `extract-audio` | POST | Endpoint family under `/api/media-asr` |
| `health` | GET | Endpoint family under `/api/media-asr` |
| `transcribe-audio` | POST | Endpoint family under `/api/media-asr` |
| `transcribe-video` | POST | Endpoint family under `/api/media-asr` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 3

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `extract_audio` | `editor` | `audio_format`, `file_id`, `folder_id`, `sample_rate`, `save_file` | Extract audio from an uploaded video file |
| `transcribe_audio` | `editor` | `file_id`, `folder_id`, `language`, `model`, `save_text` | Transcribe audio file into timestamped text |
| `transcribe_video` | `editor` | `file_id`, `folder_id`, `language`, `model`, `sample_rate`, `save_audio`, `save_text` | Extract audio from video and transcribe in one step |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `media_asr_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

Use `db_schema()` for live database details. This module must not directly read or write other modules' tables.

## Cross-Module Dependencies

- Manifest dependencies are declared in `manifest.json` when needed.
- Runtime calls to other modules must use framework capability calls, not imports or direct DB reads.

## File Access / Permission Boundary

If this module consumes `file_id`, it must validate file access through framework file access helpers or an approved public capability before reading disk.

## Frontend / Backend Structure

| Path | Status |
|---|---|
| `frontend/index.vue` | present |
| `runtime/index.ts` | present |
| `backend/router.py` | present |
| `sandbox/test_module.py` | present |
| `sandbox/package.json` | not present |

## Acceptance

<!-- DOCS-SYNC: section=sandbox -->
| Area | Status | Verification |
|---|---|---|
| README | PASS | `modules/media-asr/README.md` |
| Acceptance matrix | PASS | present |
| Backend sandbox | PASS | `PYTHONPATH=backend /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/backend/.venv/bin/python modules/media-asr/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module media-asr --check` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/media-asr/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module media-asr --check
```

## Boundaries

- Keep module business code and data inside `modules/media-asr/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
