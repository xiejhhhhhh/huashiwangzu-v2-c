# browser-tools — 浏览器工具

## Responsibility

浏览器工具

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"browser-tools"` |
| name | `"浏览器工具"` |
| category | `"tools"` |
| window_type | `"background-service"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/browser-tools"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/browser-tools` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/browser-tools`

| Family | Methods | Purpose |
|---|---|---|
| `click` | POST | Endpoint family under `/api/browser-tools` |
| `close` | POST | Endpoint family under `/api/browser-tools` |
| `download` | POST | Endpoint family under `/api/browser-tools` |
| `health` | GET | Endpoint family under `/api/browser-tools` |
| `list-links` | POST | Endpoint family under `/api/browser-tools` |
| `open` | POST | Endpoint family under `/api/browser-tools` |
| `read-text` | POST | Endpoint family under `/api/browser-tools` |
| `screenshot` | POST | Endpoint family under `/api/browser-tools` |
| `type` | POST | Endpoint family under `/api/browser-tools` |
| `wait-for` | POST | Endpoint family under `/api/browser-tools` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 9

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `click` | `viewer` | `selector`, `session_id`, `text`, `timeout` | 点击页面元素。支持 CSS selector 或按可见文本点击。 |
| `close` | `viewer` | `session_id` | 关闭浏览器会话，释放隔离上下文资源。 |
| `download` | `viewer` | `session_id`, `timeout`, `url` | 下载文件到工作区。支持浏览器上下文下载或直链 HTTP 下载；session_id 与 url 至少提供一个。 |
| `list_links` | `viewer` | `session_id` | 列出当前页面的可见链接（不含 Cookie/隐私数据）。 |
| `open` | `viewer` | `height`, `session_id`, `timeout`, `url`, `width` | 在隔离浏览器中打开 URL。适用于 JS 渲染页面、登录态页面。Cookie/localStorage 不返回给调用方。 |
| `read_text` | `viewer` | `session_id` | 提取当前页面的可见文本内容（截断保护）。返回标题/URL/可见文本。 |
| `screenshot` | `viewer` | `full_page`, `session_id` | 截图并保存到工作区（非 base64）。用 terminal-tools:publish 交付桌面。 |
| `type` | `viewer` | `selector`, `session_id`, `text`, `timeout` | 向输入框输入文本。先清空再输入，带打字延迟。 |
| `wait_for` | `viewer` | `selector`, `session_id`, `timeout`, `wait_for_navigation` | 等待页面元素出现/导航完成。 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `browser_tools_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

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
| `runtime/index.ts` | not present |
| `backend/router.py` | present |
| `sandbox/test_module.py` | present |
| `sandbox/package.json` | not present |

## Acceptance

<!-- DOCS-SYNC: section=sandbox -->
| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `modules/browser-tools/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="browser-tools", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/browser-tools/sandbox/test_module.py` |
| Frontend sandbox | SKIP | `N/A` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module browser-tools --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/browser-tools/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module browser-tools --check
```

## Boundaries

- Keep module business code and data inside `modules/browser-tools/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
