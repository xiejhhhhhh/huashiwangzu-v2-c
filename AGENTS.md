# Huashiwangzu V2 Agent Rules

## Start Order

1. Read `开发文档/README.md`.
2. Read `开发文档/agent_handoff/START_HERE.md`.
3. Read the matching task document:
   - framework: `开发文档/01_框架开发文档/README.md`
   - backend/platform: `开发文档/02_底层开发文档/README.md`
   - module: `开发文档/03_模块开发文档/README.md` and `modules/{module}/README.md`
4. Use the project toolkit MCP before changing code.

## Project Boundary

```text
frontend/   Desktop shell frontend
backend/    Platform service layer
modules/    Business modules and desktop apps
开发文档/    Current user-facing docs
```

- V2 is a clean rebuild, not a patch on V1.
- V1 reference is read-only: `../华世王镞_v1/`.
- Framework capabilities belong in `frontend/` or `backend/`.
- Business capabilities belong in `modules/`.

## Hard Rules

1. Outside `开发文档/`, directory names and file names must be English.
2. Python code uses English names, type annotations, and Router -> Schema -> Service -> Model layering.
3. API responses use `{ "success": true, "data": ..., "error": ... }`; business failures must not be fake-success HTTP 200 responses.
4. Module tasks may only change `modules/{module}/` unless the user explicitly assigns a framework task.
5. Modules must not import other modules or directly read/write other modules' tables.
6. Cross-module calls must use the framework path: frontend `platform.modules.call/capabilities`; backend `/api/modules/call` and registered capabilities.
7. Runtime capability registration is the authority; manifest `public_actions` is discovery metadata and must not drift.
8. Framework interfaces must not grow for one module's business needs. Shared framework APIs require a separate framework task.
9. Modules may use approved framework services: DB session, auth dependency, unified exceptions, file access helpers, task worker, model gateway, and capability registry.
10. Any `file_id` content read must pass framework file access checks (`check_file_access` or an approved public capability) before reading disk.
11. Multi-worker shared state must be persisted in DB or atomically written files; process memory is not shared.
12. Terminal tools run locally in the user's workspace boundary; they do not point at the host desktop. Draft outputs must be explicitly published.
13. Test data must have a marker and cleanup path. Whoever creates it cleans it.
14. Temporary task docs, execution letters, audit notes, and feedback logs must not become long-lived docs. Distill useful rules into README/agent_handoff/module README, then delete the temporary file.
15. Do not restore `后端/`, `脚本/`, `部署/`, `backend/_废弃/`, or `backend/脚本/`.

## TypeScript Rules

1. Do not use `any`, `as any`, `@ts-ignore`, or broad suppressions to bypass type checks.
2. Frontend fields must match backend response names exactly; map explicitly at the consumer when needed.
3. `转中文()` is display-only and must not change data field names.

## Toolkit Workflow

Standard chain:

```text
brief -> plan_task -> worktree_guard -> code_explore/code_node/code_impact
-> routes/capabilities/db_schema -> edit -> lint/run_test/probe/call_capability
-> docs_audit/docs_sync when contracts changed -> finish_task
```

Rules:

- Prefer CodeGraph (`code_explore`, `code_node`, `code_impact`) before grep/manual scanning.
- Use `routes`, `capabilities`, and `db_schema` instead of guessing contracts.
- Use `probe` and `call_capability` against the live system for behavior verification.
- Run `docs_audit` after changing manifest, register_capability, routers, models, sandbox, release gate, or toolkit tools. Fix drift with `docs_sync` or manual docs updates.
- `memory_write` and `mcp_feedback` are optional runtime/tooling records, not user-facing documentation.

## Testing Rules

1. The live stack is a standing fixture: backend `33000`, frontend `5173`. Tests access it; they do not rebuild it per test.
2. Playwright uses one login storageState; tests must not log in repeatedly.
3. Use conditional waits; avoid hard sleeps.
4. Prefer black-box live checks (`probe`, `call_capability`) for backend behavior. UI tests use Playwright.
5. Code changes require relevant verification. Backend changes default to backend pytest or focused `run_test`; frontend changes default to build or targeted UI checks.

## Scan Boundaries

Allowed:

```text
backend/app
backend/tests
frontend/src
modules
开发文档
dev_toolkit
```

Do not scan:

```text
frontend/node_modules
backend/.venv
backend/venv
.git
__pycache__
*.pyc
```
