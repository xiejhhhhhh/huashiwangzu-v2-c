# office-gen — Office Document Generator

Office generation module for docx, xlsx, pptx, pdf, Content IR aliases, and artifact generation.

## 对外能力

| 能力 | 说明 |
|------|------|
| `convert` | Convert an existing office file from one format to another (e.g. pptx→pdf, docx→pdf) using LibreOffice headless |
| `docx` | Generate a Word (.docx) document from structured JSON and save it to the file system |
| `export_to_artifact` | Export an existing office file as an artifact for version management |
| `generate_to_artifact` | Generate an office file and return as an artifact (no file-name conflict) |
| `pdf` | Generate a PDF document from structured JSON (same schema as docx) and save it to the file system |
| `pptx` | Generate a PowerPoint (.pptx) presentation from structured JSON and save it to the file system |
| `replace_existing` | Generate an office file and replace an existing file entry |
| `xlsx` | Generate an Excel (.xlsx) spreadsheet from structured JSON and save it to the file system |

## 接口

后端前缀：`/api/office-gen`

| 路径族 | 方法 |
|------|------|
| /convert | POST |
| /docx | POST |
| /health | GET |
| /pdf | POST |
| /pptx | POST |
| /xlsx | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/office-gen/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module office-gen --check
```
