# Project Toolkit MCP

The project toolkit is the standard MCP entry for Agent development.

## Entry

The repository root `.mcp.json` starts:

```text
python3.14 dev_toolkit/server.py
```

`server.py` only starts MCP, builds the tool list, and routes calls to component modules.

## Standard Workflow

```text
brief -> plan_task -> worktree_guard -> evidence -> edit -> verify -> docs_audit -> finish_task
```

| Stage | Tools |
|---|---|
| Overview | `brief`, `plan_task`, `worktree_guard` |
| Code facts | `code_explore`, `code_node`, `code_impact` |
| Contracts | `routes`, `capabilities`, `db_schema`, `capability_contract_diff` |
| Edits | `quick_fix_preview`, `quick_fix_patch`, batch/edit recipes |
| Verification | `lint`, `run_test`, `probe`, `call_capability`, `tail_log` |
| Docs guard | `docs_snapshot`, `docs_audit`, `docs_sync` |
| Release | `smoke_all`, `release_gate`, `module_sandbox_matrix` |
| Finish | `finish_task` |

## Docs Guard

| Tool | Purpose |
|---|---|
| `docs_snapshot` | Return code-derived facts from manifests, capabilities, sandbox metadata, and docs. |
| `docs_audit` | Report docs drift, deleted-doc references, stale public action counts, and historical garbage in long-lived docs. |
| `docs_sync` | Refresh generated sections such as `CURRENT_STATE.md`, `MODULE_MAP.md`, and module README sync blocks. |

Run docs guard after changing manifests, registered capabilities, routers, models, sandbox tests, release gate, or toolkit tools.

Operating sequence:

1. Run `docs_audit` before finishing the task.
2. If generated facts drift, run `docs_sync` with the smallest useful scope.
3. If policy/contract prose changed, update the owning README or `agent_handoff` document manually.
4. Run `docs_audit` again.
5. Do not handwrite long manifest/routes/capabilities/schema-derived facts when toolkit tools can derive them.

Supported `docs_sync` scopes:

| Scope | Writes |
|---|---|
| `current_state` | `开发文档/agent_handoff/CURRENT_STATE.md` |
| `module_map` | `开发文档/agent_handoff/MODULE_MAP.md` |
| `module_readmes` | Existing `DOCS-SYNC` blocks in module README files |
| `all` | All generated docs/blocks above |

## Memory and Feedback Records

`memory_write`, `memory_recent`, `memory_search`, `mcp_feedback`, and `mcp_feedback_summary` use the configured `memory_dir`. The default is:

```text
backend/logs/project_memory
```

These files are local runtime/tooling records, not canonical user-facing documentation. Do not copy them into `开发文档/`. If a memory or feedback item contains a durable rule, distill that rule into `AGENTS.md`, `README.md`, `开发文档/agent_handoff/`, or the owning module README, then leave the raw record in runtime storage.

## Component Rule

New tools must live in a component file:

```text
dev_toolkit/{domain}_tools.py
  tool_definitions()
  handles_tool(name)
  handle_tool(repo_root, name, arguments)
```

Do not add large schemas or business implementation blocks directly to `server.py`.

## High-Risk Tools

- `workspace_reset` deletes workspace data and requires explicit confirmation.
- `clear_log` truncates logs.
- `sql` is read-only by design.
- `probe` and `call_capability` hit the live backend.
- `docs_sync` writes Markdown generated sections.

## Release Gate Modes

Fast preflight:

```bash
python3.14 dev_toolkit/release_gate.py --preflight --skip-ui
```

Backend/sandbox full gate without UI:

```bash
python3.14 dev_toolkit/release_gate.py --skip-ui
```

Full release gate with UI:

```bash
python3.14 dev_toolkit/release_gate.py
```

`--preflight` skips full smoke/model fallback/sandbox execution. `--skip-ui` skips Playwright UI validation. Skipped checks must be reported as debt, not pass.

## Validation

```bash
python3.14 dev_toolkit/release_gate.py --preflight --skip-ui
python3.14 dev_toolkit/module_sandbox_matrix.py --json
```
