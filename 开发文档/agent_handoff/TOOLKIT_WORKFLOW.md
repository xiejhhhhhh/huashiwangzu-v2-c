# Project Toolkit Workflow

## Start

1. `brief()` for project overview.
2. `plan_task(description, task_type, module_key)` for evidence and boundaries.
3. `worktree_guard()` before edits.

## Evidence

- `code_explore`, `code_node`, `code_impact`: code and blast radius.
- `routes(filter)`: backend endpoint contracts.
- `capabilities(module)`: module action parameters and roles.
- `db_schema(table)`: table structure.
- `bug_logs(query, severity, sources, module)`: first pass for live bug clues across backend, module, frontend, worker, and toolkit logs.
- `bug_log_files(sources, module)`: list available logs before choosing a target.
- `tail_log(module)`: raw log tail for one module.

## Edit

Prefer exact patch tools when possible:

- `quick_fix_preview`
- `quick_fix_patch`
- `batch_quick_fix_apply`

## Verify

- `lint(path)` for Python.
- `run_test(target)` for focused tests.
- `probe(method, path, body)` for HTTP.
- `call_capability(module, action, params)` for cross-module behavior.
- `docs_audit` / `docs_sync` for documentation currentness.

## Backend Restart

- After backend Python, router, capability, registry, or toolkit-server changes, run `restart_backend()`.
- `restart_backend()` is the MCP wrapper for `zsh scripts/start_backend.sh --restart`; use the script only when the MCP tool is unavailable.
- Verify with `probe(method="GET", path="/api/health")` or a focused `call_capability(...)` before handing work back.

## Docs Guard Flow

1. Run `docs_audit` after changing manifests, registered capabilities, routers, models, sandbox, release gate, or toolkit tools.
2. Run `docs_sync` only for generated facts and existing `DOCS-SYNC` blocks.
3. Manually update policy/contract prose in the owning README or `agent_handoff` doc.
4. Rerun `docs_audit` before finishing.

## Memory and Feedback

- `memory_write` and `mcp_feedback` are runtime/tooling records, not user-facing documentation.
- Default storage is `backend/logs/project_memory` via toolkit `memory_dir`.
- Do not recreate the old user-facing project-memory docs directory.
- Distill durable rules into `AGENTS.md`, `README.md`, `开发文档/agent_handoff/`, or `modules/{module}/README.md`.

## Finish

- `finish_task()` summarizes dirty state, checks boundaries, and records verification.
- Runtime memory/feedback tools may be used for tooling improvement, but they do not replace user-facing docs.
