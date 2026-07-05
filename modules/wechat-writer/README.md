# wechat-writer — 公众号写作助手

## Responsibility

WeChat writing module for prompt-managed article/draft generation and content validation workflows.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"wechat-writer"` |
| name | `"公众号写作助手"` |
| category | `"tools"` |
| window_type | `"normal"` |
| singleton | `false` |
| allow_multiple | `true` |
| show_in_launcher | `true` |
| show_on_desktop | `false` |
| route_prefix | `"/api/wechat-writer"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/wechat-writer` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/wechat-writer`

| Family | Methods | Purpose |
|---|---|---|
| `article` | POST | Endpoint family under `/api/wechat-writer` |
| `drafts` | DELETE/GET/POST/PUT | Endpoint family under `/api/wechat-writer` |
| `outline` | POST | Endpoint family under `/api/wechat-writer` |
| `prompts` | DELETE/GET/POST | Endpoint family under `/api/wechat-writer` |
| `topics` | POST | Endpoint family under `/api/wechat-writer` |
| `validate` | POST | Endpoint family under `/api/wechat-writer` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 4

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `generate_article` | `editor` | `direction`, `outline`, `topic` | 根据大纲生成完整初稿 |
| `generate_outline` | `editor` | `direction`, `topic` | 根据选题生成文章大纲 |
| `generate_topics` | `editor` | `direction` | 根据产品/季节/问题肌主题生成选题建议 |
| `validate_content` | `editor` | `content` | 校验成分/功效内容的专业性 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `wechat_drafts` | Owned by `wechat-writer` module |
| `wechat_prompts` | Owned by `wechat-writer` module |

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
| `sandbox/package.json` | present |

## Acceptance

<!-- DOCS-SYNC: section=sandbox -->
| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `modules/wechat-writer/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="wechat-writer", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/wechat-writer/sandbox/test_module.py` |
| Frontend sandbox | PASS | `cd modules/wechat-writer/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module wechat-writer --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/wechat-writer/sandbox/test_module.py
cd modules/wechat-writer/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module wechat-writer --check
```

## Boundaries

- Keep module business code and data inside `modules/wechat-writer/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
