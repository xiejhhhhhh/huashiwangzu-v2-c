# Acceptance Gate

## Required For Any Code Change

1. Confirm worktree and boundaries with `worktree_guard`.
2. Gather contracts with CodeGraph plus `routes`/`capabilities`/`db_schema` as needed.
3. Run relevant lint/test/probe/capability checks.
4. Run `docs_audit` when contracts, manifests, routes, models, sandbox, release gate, or toolkit tools changed.
5. Report failures honestly; do not call a skipped check passed.

## Verification Matrix by Change Type

| Change type | Required checks | Runtime checks | Docs/release checks |
|---|---|---|---|
| Docs only | Markdown scope review | N/A | `docs_audit` |
| Module README/manifest | `capability_contract_diff(module, include_parameters=true)` | N/A unless behavior changed | `docs_audit`, `module_sandbox_matrix(check=false)` |
| Module frontend | sandbox build or targeted UI check | Browser/UI check when behavior changed | `docs_audit` if manifest/sandbox/docs changed |
| Module backend/capability | lint changed Python, module sandbox test if present | `call_capability` or module HTTP probe | `capability_contract_diff`, `docs_audit`, `module_sandbox_matrix(check=false)` |
| Parser / Content IR | parser sandbox test, focused backend test | Probe representative file/content flow | `docs_audit` if public contract changed |
| Backend/platform route/service/model | focused backend pytest or justified alternative | `probe` changed endpoints | `docs_audit`, release preflight |
| Framework frontend/runtime | frontend build or targeted Playwright | Live UI check with storageState login | `docs_audit` if runtime contract changed |
| Dev toolkit / MCP | lint changed toolkit Python | Tool call smoke for changed tool | `docs_audit`, release preflight |
| Release gate / sandbox tooling | lint changed toolkit Python | Run affected gate/matrix command | `release_gate`, `module_sandbox_matrix`, `docs_audit` |

## Module Tasks

- Changes stay inside `modules/{module}/` unless a framework task is explicitly assigned.
- `capability_contract_diff(module, include_parameters=true)` must pass when public actions or capability code can be affected.
- `module_sandbox_matrix(check=false)` must show README acceptance metadata.
- If backend exists, run or justify `modules/{module}/sandbox/test_module.py`.
- Validate live behavior with `call_capability` or module HTTP probes when behavior changes.

## Framework / Backend Tasks

- Run focused backend tests or explain why not applicable.
- Keep unified API envelope and semantic failure rules.
- Use live probes for changed endpoints.
- If public contracts change, update `agent_handoff/CONTRACTS.md` and affected README files.

## Frontend Tasks

- Run build or targeted UI checks.
- Use storageState login for Playwright.
- Use conditional waits; no hard sleeps unless explicitly justified.

## Release Gate Modes

Fast preflight before reporting general readiness:

```bash
python3.14 dev_toolkit/release_gate.py --preflight --skip-ui
```

Backend/sandbox full gate without UI:

```bash
python3.14 dev_toolkit/release_gate.py --skip-ui
```

Full release gate with UI when frontend behavior matters:

```bash
python3.14 dev_toolkit/release_gate.py
```

`--preflight` skips full smoke/model fallback/sandbox execution. `--skip-ui` skips Playwright UI validation. Skipped checks are debt, not pass.

A known blocker such as test-data pollution must be reported as blocker, not hidden.
