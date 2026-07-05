# 模块开发文档

模块是桌面里的软件和插件。业务功能优先放入 `modules/`，不要塞进框架。

## Module Contract

| Area | Rule |
|---|---|
| Code location | `modules/{key}/` |
| Manifest | `modules/{key}/manifest.json` declares desktop/runtime metadata |
| Backend API | `modules/{key}/backend/router.py` |
| Frontend entry | `modules/{key}/frontend/index.vue` |
| Runtime | `modules/{key}/runtime/index.ts` |
| Sandbox | `modules/{key}/sandbox/` |
| Long-lived docs | `modules/{key}/README.md` only |

## Data And Interaction Rules

- Module business tables use the module prefix, for example `kb_*`, `agent_*`, `memory_*`.
- Modules do not directly read/write `framework_*` or other module tables.
- Modules do not add database foreign keys to framework or other module tables.
- Cross-module calls must use framework capability routes.
- Framework data access goes through public framework APIs or approved service helpers.

## Backend Capability Contract

- Register public capabilities with `register_capability(module, action, handler, parameters, min_role)`.
- Mirror public capabilities in `manifest.public_actions`.
- Validate with `capability_contract_diff(module, include_parameters=true)`.
- `/api/modules/call` uses `target_module`, `action`, and `parameters`.

## New Module Flow

```bash
cp -r modules/_template modules/your-module-key
# edit manifest/runtime/frontend/backend as needed
cd modules/your-module-key/sandbox && npm run build
cd frontend && npm run build
```

If the module has backend capabilities, add `sandbox/test_module.py` and verify it with the backend virtualenv.

## Target Structure

```text
modules/{module}/
  manifest.json
  README.md
  frontend/index.vue
  runtime/index.ts
  backend/router.py          # optional
  backend/schemas.py         # optional
  backend/models.py          # optional
  backend/services/          # optional
  sandbox/test_module.py     # backend contract tests when backend exists
  sandbox/package.json       # frontend sandbox when UI exists
```

## README Template

Every module README should describe current behavior only:

```text
Responsibility
Manifest Contract
Current Capabilities
HTTP API / Endpoint Families
Public Actions / Capability Contract
Data Ownership
Cross-Module Dependencies
File Access / Permission Boundary
Frontend / Backend Structure
Acceptance
Reproducible Checks
Boundaries
```

No task logs, execution letters, dated audit notes, or historical repair reports.

## Sandbox Acceptance

| Module type | Required verification |
|---|---|
| UI-only | frontend sandbox build or main frontend build |
| Backend capability | `PYTHONPATH=backend backend/.venv/bin/python modules/{key}/sandbox/test_module.py` |
| Parser | real sample files and blocks/resources/metadata assertions |
| Live integration | `probe` or `call_capability` against the main backend |

Run the matrix:

```bash
python3.14 dev_toolkit/module_sandbox_matrix.py --json
```

## Parser / Content IR

Parser outputs should align with Content IR:

| Field | Requirement |
|---|---|
| `file_id` | Source framework file ID |
| `format` | Lowercase format/extension |
| `blocks` | English block types |
| `resources` | Binary/resource references when present |
| `metadata` | Parser, quality, truncation, warnings |
| `warnings` | Recoverable issues; failures must not be fake success |

## Runtime Boundary

Module frontend code uses its runtime/platform object and must not import desktop shell internals. Module backend code may use approved framework DB/auth/response/file/task/gateway/capability services, but business logic and tables stay in the module.

## Documentation Rule

Temporary plans, audit notes, and execution letters are deleted after useful rules are distilled into the relevant README.
