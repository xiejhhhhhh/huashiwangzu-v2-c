# Current State

Last generated: 2026-07-05T13:36:28.965637+00:00

This file is generated from current repository facts. Refresh it with `docs_sync(scope="current_state")`.

## Services

| Item | Current contract |
|---|---|
| Backend | FastAPI on `127.0.0.1:33000`, actual port recorded in `backend/logs/.backend.port` |
| Frontend | Vite dev server on `127.0.0.1:5173` |
| Database | PostgreSQL 17 + pgvector, DB name `华世王镞_v2` |
| Embeddings | bge-m3 OpenAI-compatible endpoint on `127.0.0.1:30000` |

## Code-derived status

| Check | Value |
|---|---|
| Modules with manifests | 35 |
| Public capabilities in manifests | 189 |
| Capability drift | {'checked_modules': 36, 'ok_modules': 29, 'modules_with_drift': 0, 'uncheckable_sites': 0} |

## Current known release risk

Run `release_gate(skip_ui=true, mode="preflight")` for live status. As of the last manual audit, test data pollution may still block a clean release; treat the live gate result as the authority.
