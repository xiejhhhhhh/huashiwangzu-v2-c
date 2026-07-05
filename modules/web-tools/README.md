# web-tools — 联网工具

## Responsibility

联网工具

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"web-tools"` |
| name | `"联网工具"` |
| category | `"tools"` |
| module_type | `"provider"` |
| module_family | `"web"` |
| product_status | `"background"` |
| window_type | `"background-service"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/web-tools"` |
| contract_version | `"2.0"` |
| module_version | `"1.0.0"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/web-tools` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/web-tools`

| Family | Methods | Purpose |
|---|---|---|
| `fetch` | POST | Endpoint family under `/api/web-tools` |
| `health` | GET | Endpoint family under `/api/web-tools` |
| `search` | POST | Endpoint family under `/api/web-tools` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 2

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `fetch` | `viewer` | `max_chars`, `url` | 抓取指定网址正文文本(无需API key)。自动过滤 script/style/nav/footer。含SSRF防护，拒绝内网地址。 |
| `search` | `viewer` | `query`, `top_k` | 联网搜索网页,返回标题/链接/摘要(无需API key)。基于 DuckDuckGo HTML 端点。 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `web_tools_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

Use `db_schema()` for live database details. This module must not directly read or write other modules' tables.

## Cross-Module Dependencies

- Manifest dependencies are declared in `manifest.json` when needed.
- Runtime calls to other modules must use framework capability calls, not imports or direct DB reads.

## File Access / Permission Boundary

If this module consumes `file_id`, it must validate file access through framework file access helpers or an approved public capability before reading disk.

## Frontend / Backend Structure

| Path | Status |
|---|---|
| `frontend/index.vue` | not present |
| `runtime/index.ts` | present |
| `backend/router.py` | present |
| `sandbox/test_module.py` | present |
| `sandbox/package.json` | not present |

## Acceptance

<!-- DOCS-SYNC: section=sandbox -->
| Area | Status | Verification |
|---|---|---|
| README | PASS | `modules/web-tools/README.md` |
| Acceptance matrix | PASS | present |
| Backend sandbox | PASS | `PYTHONPATH=backend /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/backend/.venv/bin/python modules/web-tools/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module web-tools --check` |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/web-tools/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module web-tools --check
```

## Boundaries

- Keep module business code and data inside `modules/web-tools/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
