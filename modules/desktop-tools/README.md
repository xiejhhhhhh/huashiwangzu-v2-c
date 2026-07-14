# desktop-tools — Desktop Tools

假桌面文件工具：列目录、搜索、读文件内容（路由到各解析器）、写文件、发布产物到桌面。

## 对外能力

| 能力 | 说明 |
|------|------|
| `copy_file` | Copy a file. |
| `create_file` | Create a new file with text content. |
| `delete_file` | Soft-delete a file. |
| `get_file` | Get a single file's metadata by file_id. |
| `list_apps` | List desktop applications available to the current user. |
| `list_files` | List files in a folder (or root). Returns file name, type, size, and id. |
| `list_versions` | List file versions (via artifact). |
| `open_file` | Open or preview a desktop file by file_id. Returns app://file/open plus a client_action for the desktop shell. |
| `publish_artifact` | Publish an artifact to the desktop as a file. |
| `read_file` | Read file content by file_id. Routes to format parsers (PDF, DOCX, XLSX, etc.) and returns text content capped at 20000 chars with truncation metadata. |
| `refresh` | Trigger desktop file list refresh. |
| `rename_file` | Rename a file. |
| `replace_file` | Replace file content from text, artifact, or another file. No base64 needed. |
| `replace_file_from_artifact` | Replace a desktop file using content from an artifact. No base64 needed. |
| `restore_version` | Restore a file to a previous version. |
| `search_files` | Search files by keyword and/or extension. Returns matching file metadata. |

## 接口

后端前缀：`/api/desktop-tools`

| 路径族 | 方法 |
|------|------|
| /health | GET |
| /list-apps | GET |
| /list-files | POST |
| /read-file | POST |
| /search-files | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/desktop-tools/sandbox/test_module.py
cd modules/desktop-tools/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module desktop-tools --check
```
