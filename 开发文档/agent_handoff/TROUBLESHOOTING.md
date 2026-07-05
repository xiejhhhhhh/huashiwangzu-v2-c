# Troubleshooting

## Backend 500

1. `probe` the failing endpoint.
2. `tail_log("backend")`.
3. `routes(filter)` to confirm method/path/body.
4. `code_explore` the router/service.
5. Run focused `run_test` if a test exists.

## Capability Call Fails

1. `capabilities(module)`.
2. `capability_contract_diff(module, include_parameters=true)`.
3. Confirm request body uses `parameters`, not `params`.
4. `call_capability(module, action, params)` with the correct role.
5. `tail_log("backend")`.

## Release Gate Blocked

- Capability drift: fix manifest or runtime registration.
- README matrix/docs drift: run `docs_sync` or update the affected README.
- Test data pollution: audit and clean test artifacts with explicit confirmation.
- Queue failures: classify active/new failures separately from historical debt.

## UI Looks Empty

Do not assume empty means success. Check loading/error/stale states, network responses, and console errors.

## File Access Fails

Check owner/share access and ensure code uses framework file access helpers before disk reads.
