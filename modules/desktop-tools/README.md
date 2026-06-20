# Desktop Tools Module

A **bridge module** that exposes the framework's desktop/file capabilities to the Agent via the cross-module capability registry. The Agent's tool discovery (`tool_discovery.build_tools`) automatically discovers these capabilities and converts them into LLM function-calling tools — **zero Agent code changes required**.

## Skills Exposed

| Skill | Description | Backend |
|-------|-------------|---------|
| `desktop-tools:list_files` | List files in a folder (or root) | Framework file service |
| `desktop-tools:search_files` | Search files by keyword / extension | Framework file service |
| `desktop-tools:read_file` | Read file content (routes to format parsers) | Parser modules via `call_capability` |
| `desktop-tools:list_apps` | List desktop applications | Framework app registry |

## Key Design

### Owner Isolation

All capabilities enforce **owner isolation** — a caller can only access their own files/apps. The `caller` string (e.g. `"user:42"`) is parsed to extract the user ID, and all database queries filter by `owner_id`.

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
cd modules/desktop-tools && python3 sandbox/test_module.py

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
cd modules/desktop-tools
python3 sandbox/test_module.py
```
