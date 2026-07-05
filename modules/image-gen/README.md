# image-gen — Image Generation

## Responsibility

Image generation module with provider templates, prompt translation, generation records, and usage history.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"image-gen"` |
| name | `"Image Generation"` |
| category | `"tools"` |
| window_type | `"normal"` |
| singleton | `false` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/image-gen"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/image-gen` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/image-gen`

| Family | Methods | Purpose |
|---|---|---|
| `generate` | POST | Endpoint family under `/api/image-gen` |
| `health` | GET | Endpoint family under `/api/image-gen` |
| `history` | GET | Endpoint family under `/api/image-gen` |
| `templates` | GET | Endpoint family under `/api/image-gen` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 3

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `generate` | `editor` | `aspect_ratio`, `count`, `prompt`, `size`, `steps`, `template` | 生成图片：根据提示词生成产品图、海报、配图等（多服务商模板，支持LiblibAI星流/GPTStore/占位图降级） |
| `list_templates` | `viewer` | none | 列出可用生图模板（服务商+模型），含凭据是否齐全标识 |
| `usage_history` | `editor` | `limit` | 查询本人的生图历史记录，含积分消耗 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `imagegen_records` | Owned by `image-gen` module |

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
| Manifest contract | PASS | `modules/image-gen/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="image-gen", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/image-gen/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module image-gen --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/image-gen/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module image-gen --check
```

## Boundaries

- Keep module business code and data inside `modules/image-gen/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
