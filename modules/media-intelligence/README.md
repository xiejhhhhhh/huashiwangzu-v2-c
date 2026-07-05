# media-intelligence — Media Intelligence

## Responsibility

Media Intelligence

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"media-intelligence"` |
| name | `"Media Intelligence"` |
| category | `"tools"` |
| module_type | `"orchestrator"` |
| module_family | `"media"` |
| product_status | `"active"` |
| window_type | `"normal"` |
| singleton | `false` |
| allow_multiple | `false` |
| show_in_launcher | `true` |
| show_on_desktop | `false` |
| route_prefix | `"/api/media-intelligence"` |
| contract_version | `"2.0"` |
| module_version | `"0.1.0"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/media-intelligence` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/media-intelligence`

| Family | Methods | Purpose |
|---|---|---|
| `analyze-image` | POST | Endpoint family under `/api/media-intelligence` |
| `analyze-video` | POST | Endpoint family under `/api/media-intelligence` |
| `detect-objects` | POST | Endpoint family under `/api/media-intelligence` |
| `embed-image` | POST | Endpoint family under `/api/media-intelligence` |
| `extract-keyframes` | POST | Endpoint family under `/api/media-intelligence` |
| `health` | GET | Endpoint family under `/api/media-intelligence` |
| `ocr` | POST | Endpoint family under `/api/media-intelligence` |
| `summarize-media` | POST | Endpoint family under `/api/media-intelligence` |
| `vlm-refine` | POST | Endpoint family under `/api/media-intelligence` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 8

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `analyze_image` | `viewer` | `file_id`, `include_embedding`, `refine` | Analyze an uploaded image through local facts, rule-based summary, and optional VLM refine layers |
| `analyze_video` | `viewer` | `file_id`, `max_keyframes`, `refine` | Analyze an uploaded video with ffprobe metadata, timeline markers, summary, and optional VLM refine |
| `detect_objects` | `viewer` | `file_id` | Return object detections or structured degraded status when no detector is configured |
| `embed_image` | `viewer` | `dimensions`, `file_id` | Return a local image fingerprint vector for dedupe-oriented contract testing |
| `extract_keyframes` | `viewer` | `file_id`, `max_keyframes` | Extract ffprobe-derived timeline keyframe markers from a video file |
| `ocr` | `viewer` | `file_id` | Run OCR layer contract for image/video files; returns structured degraded status when OCR is not configured |
| `summarize_media` | `viewer` | `analysis`, `file_id` | Summarize a media file or existing media-intelligence analysis result |
| `vlm_refine` | `viewer` | `analysis`, `prompt` | Refine an existing media-intelligence analysis result through the VLM layer contract |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `media_intelligence_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

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
| README | PASS | `modules/media-intelligence/README.md` |
| Acceptance matrix | PASS | present |
| Backend sandbox | PASS | `PYTHONPATH=backend /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/backend/.venv/bin/python modules/media-intelligence/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module media-intelligence --check` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/media-intelligence/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module media-intelligence --check
```

## Boundaries

- Keep module business code and data inside `modules/media-intelligence/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
