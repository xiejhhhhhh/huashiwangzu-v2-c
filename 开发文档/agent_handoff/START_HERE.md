# Agent Start Here

This is the execution entry for Agent development.

## First Decision

Classify the task before reading code:

| Task | Primary docs | Allowed change area |
|---|---|---|
| Framework shell | `开发文档/01_框架开发文档/README.md` | `frontend/src`, related framework docs/tests |
| Backend/platform | `开发文档/02_底层开发文档/README.md` | `backend/app`, `backend/tests`, related docs |
| Module | `开发文档/03_模块开发文档/README.md` + `modules/{key}/README.md` | `modules/{key}/` only |
| Toolkit | `dev_toolkit/README.md` | `dev_toolkit/` and toolkit docs/tests |
| Docs | this directory and relevant README files | docs only |

## Standard Execution Chain

```text
brief -> plan_task -> worktree_guard -> code_explore/code_node/code_impact
-> routes/capabilities/db_schema -> minimal edit -> verification -> docs_audit -> finish_task
```

## Current Fact Sources

- Capabilities: `capabilities(module)` and `capability_contract_diff`.
- Routes: `routes(filter)` or OpenAPI.
- Tables: `db_schema()`.
- Module validation: `module_sandbox_matrix(check=false)`.
- Release state: `release_gate(mode="preflight", skip_ui=true)`.
- Docs currentness: `docs_audit`.

## Do Not

- Do not read historical task logs as current truth.
- Do not keep execution letters, audit reports, or feedback logs as long-lived docs.
- Do not modify framework code during a module task.
- Do not handwrite facts that can be generated from manifest/capability/routes/schema.
