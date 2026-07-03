# Desktop Tools Module

A **bridge module** that exposes the framework's desktop/file capabilities to the Agent via the cross-module capability registry. The Agent's tool discovery (`tool_discovery.build_tools`) automatically discovers these capabilities and converts them into LLM function-calling tools — **zero Agent code changes required**.

## Skills Exposed

| Skill | Description | Backend |
|-------|-------------|---------|
| `desktop-tools:list_files` | List files in a folder (or root) | Framework file service |
| `desktop-tools:search_files` | Search files by keyword / extension | Framework file service |
| `desktop-tools:read_file` | Read file content (routes to format parsers) | Parser modules via `call_capability` |
| `desktop-tools:list_apps` | List desktop applications | Framework app registry |
| `desktop-tools:get_file` | Get one file's metadata | Framework file service |
| `desktop-tools:create_file` | Create a text file in the framework file system | Framework upload service |
| `desktop-tools:replace_file` | Replace file content from text, artifact, or another file | Framework file/content services |
| `desktop-tools:delete_file` | Soft-delete a file to trash | Framework file service |
| `desktop-tools:rename_file` | Rename a file | Framework file service |
| `desktop-tools:copy_file` | Copy a file within the current user's file space | Framework file ops service |
| `desktop-tools:list_versions` | List artifact versions | Framework artifact service |
| `desktop-tools:restore_version` | Restore an artifact version | Framework artifact service |
| `desktop-tools:replace_file_from_artifact` | Replace a desktop file from artifact content | Framework artifact service |
| `desktop-tools:publish_artifact` | Publish an artifact as a desktop file | Framework artifact service |
| `desktop-tools:refresh` | Return a desktop refresh acknowledgement | Stateless bridge |

## Key Design

### Owner Isolation

All capabilities enforce **owner isolation**. File reads use framework `check_file_access`, so owner and shared-file permissions are respected before disk reads. File mutations call the framework write/delete/rename/copy services, which enforce owner or write access. The `caller` string (e.g. `"user:42"`) is parsed to extract the user ID.

### Read File Pipeline

`desktop:read_file` is the connector that chains format parser modules:

```
file_id → detect extension → call_capability("{ext}-parser", "parse", {file_id}) → unified content blocks → plain text
```

Parser mapping:

| Extension | Parser Module |
|-----------|---------------|
| `pdf` | `pdf-parser` |
| `docx` | `docx-parser` |
| `xlsx`, `xls`, `csv` | `xlsx-parser` |
| `pptx` | `pptx-parser` |
| `txt`, `md`, `markdown`, `text`, `log` | `text-parser` (or direct read fallback) |
| `json`, `xml`, `yaml`, `yml` | Direct text read |

Output is capped to protect Agent context. `read_file` returns at most 20000 text characters and at most 80 content blocks, with `truncated` and `limits` metadata when content is clipped. Parser failures for non-text formats raise a real unified API error instead of returning a fake-success payload.

### Stateless Bridge

This module stores no data. It is a pure bridge between the framework's existing capabilities and the Agent's skill discovery system.

## Agent Integration

The Agent's `tool_discovery.build_tools(role)` calls `list_capabilities(role)` which returns all registered capabilities including those from `desktop-tools`. Each capability becomes a function-calling tool that the LLM can invoke. The Agent can now answer:

- "What files are on my desktop?"
- "Find PDF files about reports"
- "Read that document"
- "What apps can I open?"

## Verification

```bash
# Run sandbox test
PYTHONPATH=backend backend/.venv/bin/python modules/desktop-tools/sandbox/test_module.py

# Check capabilities are registered (requires running backend)
curl http://127.0.0.1:33000/api/modules/capabilities | jq

# Call a capability directly
curl -X POST http://127.0.0.1:33000/api/modules/call \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"target_module":"desktop-tools","action":"list_files","parameters":{"folder_id":0}}'

# Read a PDF file via Agent chain
curl -X POST http://127.0.0.1:33000/api/modules/call \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"target_module":"desktop-tools","action":"read_file","parameters":{"file_id":42}}'
```

## Sandbox Development

```bash
# Frontend sandbox
cd modules/desktop-tools/sandbox
npm install
npm run dev

# Backend sandbox test
cd /path/to/华世王镞_v2
PYTHONPATH=backend backend/.venv/bin/python modules/desktop-tools/sandbox/test_module.py
```
