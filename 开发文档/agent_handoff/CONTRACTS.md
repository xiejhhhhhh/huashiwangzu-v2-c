# Current Contracts

## Unified API Envelope

```json
{ "success": true, "data": {}, "error": null }
```

Business errors must raise framework exceptions or return a unified failure envelope. Legacy `code != 0`, `success=false`, or `error` payloads must not be wrapped as outer success.

## Cross-Module Calls

Backend request body:

```json
{
  "target_module": "knowledge",
  "action": "search",
  "parameters": { "query": "..." }
}
```

- Backend path: `/api/modules/call`.
- Frontend path: `platform.modules.call(targetModule, action, parameters)`.
- Runtime `register_capability` is authoritative.
- Manifest `public_actions` is discovery metadata and must match runtime registration.

## Data Ownership

| Owner | Prefix |
|---|---|
| Framework | `framework_*` |
| Agent | `agent_*` |
| Knowledge | `kb_*` |
| Memory | `memory_*` |
| Excel engine | `excel_*` |
| Image generation | `imagegen_*` |
| IM | `im_*` |
| Docs open | `docs_*` |
| Douyin delivery | `douyin_*` |
| WeChat writer | `wechat_*` |
| Codemap | `codemap_*` |

Modules use logical IDs for cross-owner references. They must not add database foreign keys to framework or other module tables.

## File Access

Any endpoint or capability that reads file content by `file_id` must validate owner/share access through framework file access checks before reading disk.

## Content IR

Canonical flow:

```text
Agent / Parser -> Content IR -> validate_ir -> normalize_ir -> write_ir -> DB canonical source -> compile/publish
```

- DB is the canonical source for structured content.
- LLM output is not trusted; validators are the authority.
- Agent cannot directly create or replace framework physical files. It writes structure first and explicitly publishes artifacts/files when requested.

## Frontend Runtime

Modules use runtime/platform APIs for auth, files, office, gateway, tasks, notifications, logs, settings, and module calls. Module frontend code must not import desktop shell internals.

## Terminal Tools Boundary

Terminal execution is local but locked to `data/workspaces/{user_id}/`. Host desktop/files are not exposed. Drafts become desktop files only through explicit publish/import capabilities.
