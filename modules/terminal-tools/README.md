# terminal-tools — 终端工具

## Responsibility

Workspace-bound command and file tool module for Agent execution, run_python, charts, import, and publish.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"terminal-tools"` |
| name | `"终端工具"` |
| category | `"tools"` |
| window_type | `"background-service"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `false` |
| show_on_desktop | `false` |
| route_prefix | `"/api/terminal-tools"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/terminal-tools` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/terminal-tools`

| Family | Methods | Purpose |
|---|---|---|
| `chart` | POST | Endpoint family under `/api/terminal-tools` |
| `exec` | POST | Endpoint family under `/api/terminal-tools` |
| `health` | GET | Endpoint family under `/api/terminal-tools` |
| `import` | POST | Endpoint family under `/api/terminal-tools` |
| `list-workspace` | POST | Endpoint family under `/api/terminal-tools` |
| `publish` | POST | Endpoint family under `/api/terminal-tools` |
| `read-file` | POST | Endpoint family under `/api/terminal-tools` |
| `run-python` | POST | Endpoint family under `/api/terminal-tools` |
| `write-file` | POST | Endpoint family under `/api/terminal-tools` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 8

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `chart` | `editor` | `chart_type`, `data`, `title`, `x_label`, `y_label` | 傻瓜式出图，传入数据数组和图表类型，后端用 matplotlib 出图。 |
| `exec` | `editor` | `command`, `timeout` | 在用户工作区执行 shell 命令，返回 stdout/stderr/退出码。受路径约束、危险命令拦截、超时和输出限制。 |
| `import` | `editor` | `file_id`, `target_path` | 将框架文件系统的文件拷入工作区供 CLI 处理，owner 校验。 |
| `list_workspace` | `viewer` | `path` | 列出用户工作区内的文件和目录。 |
| `publish` | `editor` | `filename`, `folder_id`, `path` | 将工作区文件显式交付到框架文件系统（桌面可见），享受框架内容去重。 |
| `read_file` | `viewer` | `path` | 读用户工作区内的文件内容。 |
| `run_python` | `editor` | `code`, `input_files`, `timeout` | 在用户工作区子进程执行 Python 数据分析代码。预置 pandas/numpy/matplotlib。 |
| `write_file` | `editor` | `content`, `path` | 写文件到用户工作区，路径自动约束在工作区内。 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `terminal_tools_*` | No SQLAlchemy table detected in module backend, or UI-only/stateless module |

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
| Manifest contract | PASS | `modules/terminal-tools/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="terminal-tools", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/terminal-tools/sandbox/test_module.py` |
| Frontend sandbox | PASS | `cd modules/terminal-tools/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module terminal-tools --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/terminal-tools/sandbox/test_module.py
cd modules/terminal-tools/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module terminal-tools --check
```

## Boundaries

- Keep module business code and data inside `modules/terminal-tools/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
