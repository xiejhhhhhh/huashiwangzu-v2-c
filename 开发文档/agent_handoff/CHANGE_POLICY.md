# Change Policy

## Task Boundaries

| Task | Allowed paths | Notes |
|---|---|---|
| Framework frontend | `frontend/src`, framework docs/tests | Do not add module business logic. |
| Backend/platform | `backend/app`, `backend/tests`, platform docs | Keep API envelope and stable contracts. |
| Module | `modules/{module}/` | Do not modify framework or other modules. |
| Toolkit | `dev_toolkit/` | New tools must be componentized. |
| Docs | `AGENTS.md`, `README.md`, `开发文档/`, `modules/*/README.md` | Keep docs current and concise. |

## Upgrade Rules

- If a module needs a new common framework capability, create a separate framework task.
- If a change touches multiple modules, define the shared contract first.
- If manifest, registered capabilities, routes, models, sandbox, or release gate change, run `docs_audit` and update docs.

## Documentation Retention

Long-lived docs describe current behavior only. Temporary work material is deleted after useful rules are distilled.

| Category | Action | Examples |
|---|---|---|
| Current operating rules | Keep and update | `AGENTS.md`, root `README.md`, `开发文档/README.md`, `agent_handoff/*.md` |
| Current development handbooks | Keep and update | framework/backend/module READMEs, `dev_toolkit/README.md`, `modules/*/README.md` |
| Code-derived facts | Refresh, do not handwrite long tables | `CURRENT_STATE.md`, `MODULE_MAP.md`, module README `DOCS-SYNC` blocks |
| Temporary task prompts | Delete after distill | execution letters, research letters, audit letters, repair prompts |
| Historical logs | Delete after distill | changelogs, dated reports, delivery notes, one-off verification reports |
| Tooling records | Keep outside user docs | `backend/logs/project_memory`, tool usage logs, MCP feedback records |
| Unprocessed feedback | Keep until handled | actionable feedback that has not been distilled into a rule or task |

## Distillation Rule

1. Extract durable rules, commands, contracts, or gotchas.
2. Put them into the owning README or `agent_handoff` document.
3. Delete the raw prompt/report/log from long-lived docs.
4. Run `docs_audit` if references, contracts, manifests, sandbox metadata, or toolkit behavior changed.

Never recreate the old user-facing project-memory docs directory as a documentation store. Runtime memory and feedback belong under the configured toolkit memory directory, default `backend/logs/project_memory`.
