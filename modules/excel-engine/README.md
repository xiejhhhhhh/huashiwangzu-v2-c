# excel-engine — Excel 编辑器

Spreadsheet engine for parsing, workbook state, edits, history, versions, export, compile, and desktop publish.

## 对外能力

| 能力 | 说明 |
|------|------|
| `append_rows` | Append rows to the end of a sheet |
| `compile_xlsx` | Compile workbook to temporary XLSX for download without creating a file record |
| `create_workbook` | Create a new empty workbook in the database |
| `export_xlsx` | Export workbook to XLSX file |
| `import_file_to_workbook` | Import a file into a database workbook for editing |
| `list_history` | List operation history for a workbook |
| `list_versions` | List saved versions of a workbook |
| `parse` | Parse XLSX/CSV files into cell data |
| `publish_to_desktop` | Publish workbook to desktop |
| `redo` | Redo the last undone operation |
| `restore_version` | Restore a workbook to a saved version |
| `undo` | Undo the last operation |
| `update_range` | Update a range of cells |

## 接口

后端前缀：`/api/excel-engine`

| 路径族 | 方法 |
|------|------|
| /clipboard | POST |
| /dispatch | POST |
| /download | GET |
| /edit | POST |
| /export | POST |
| /health | GET |
| /open | POST |
| /parse | POST |
| /state | POST |
| /style | POST |
| /table | POST |

## 数据表

| 表名 |
|------|
| `excel_cells` |
| `excel_col_widths` |
| `excel_history` |
| `excel_redo_stack` |
| `excel_row_heights` |
| `excel_sheets` |
| `excel_versions` |
| `excel_workbooks` |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/excel-engine/sandbox/test_module.py
cd modules/excel-engine/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module excel-engine --check
```
