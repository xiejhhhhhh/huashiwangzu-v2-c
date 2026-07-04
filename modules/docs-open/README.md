# docs-open — document open API facade

## Responsibility

`docs-open` provides a document open facade for the desktop shell and other modules. It issues scoped open tokens, returns document metadata/content endpoints, renders embedded editor/viewer pages, and delegates file conversion or creation to framework services and public module capabilities.

Docs-open tokens are scoped bearer alternatives for one or more document IDs. They are reusable until expiry or explicit revoke, but they are not full login tokens: issuing/opening/creating/exporting/revoking documents requires the framework JWT bearer token.

## Public capabilities

- `docs-open:open`
  - Parameters: `file_id: int`, `mode: string`
  - Returns: document metadata including `id`, `title`, `type`, `category`, `editor`, and `mime`
  - Min role: `viewer`
- `docs-open:get_content`
  - Parameters: `file_id: int`
  - Returns: structured JSON content for the requested document
  - Min role: `viewer`
- `docs-open:create_doc`
  - Parameters: `title: string`, `type: string`
  - Returns: created file metadata including `id`, `title`, and `type`
  - Min role: `editor`

## HTTP endpoints

Router prefix: `/api/docs`

- `POST /api/docs/token` — issue a scoped docs-open token with a non-empty `scope.doc_ids` or `scope.edit_doc_ids`; JWT bearer only.
- `POST /api/docs/open` — open an existing framework file and return embed/content URLs; JWT bearer only.
- `POST /api/docs` — create a new empty document; JWT bearer only.
- `GET /api/docs/{file_id}/content` — read the JSON middle-layer document content; JWT bearer or scoped docs-open token.
- `POST /api/docs/{file_id}/content` — write JSON middle-layer content; JWT bearer or scoped docs-open token with edit scope.
- `POST /api/docs/{file_id}/export` — export or convert a document, delegating office formats to `office-gen:convert`; JWT bearer only.
- `GET /api/docs/embed/{file_id}` — render an embedded HTML editor/viewer page after token triple validation.
- `GET /api/docs/{file_id}/file` — return the underlying file after docs token query checks or JWT bearer checks.
- `POST /api/docs/{file_id}/revoke-tokens` — revoke active docs-open tokens for a file; JWT bearer only.

## Data tables

- `docs_open_token`
  - `client_id`, `open_id`: token subject and client identity.
  - `access_token_hash`, `token_prefix`: stored token verifier and short display prefix.
  - `scope`: JSON scope such as allowed document IDs.
  - `expires_at`, `is_revoked`, `created_at`: token lifecycle fields.

## How to query/use

Use the framework cross-module path instead of importing this module directly:

```python
result = await call_capability(
    "docs-open",
    "open",
    {"file_id": file_id, "mode": "view"},
    caller=f"user:{user_id}",
    caller_role="viewer",
)
```

For HTTP clients, call `/api/docs/open` to obtain an `embed_url` and `/api/docs/{file_id}/content` URL. All file access must pass framework `check_file_access` or docs-open token validation before content or file bytes are returned.

## Boundaries/notes

- This module is a facade, not an editor implementation. Office generation/conversion is delegated to `office-gen`; file creation and framework file access stay in framework services.
- Cross-module capabilities resolve the caller from `user:{id}` and enforce file access checks before reading content.
- Embedded HTML generation is intentionally isolated in handlers and should continue using safe value injection and CSP headers.
- Content writes currently update text-like files and CSV through framework content-addressed replacement. Office binary writes are rejected instead of pretending success until a true replace-back contract exists.

## Sandbox validation

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/docs-open/sandbox/test_module.py
```

The sandbox test covers token scope/expiry/client ID boundaries, mode and document type normalization, token hashing, capability return shapes, and the scoped-token-vs-JWT boundary.

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `docs-open`, window `normal`, formats: Not format-bound. |
| Backend capability | PASS | 3 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Uses framework file APIs or capability bridge; file_id paths must preserve check_file_access. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/docs-open/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `docs-open:<action>` and release smoke/capability drift gates. |
| Known debt | PASS | None tracked in this matrix. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/docs-open/sandbox/test_module.py
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module docs-open --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
