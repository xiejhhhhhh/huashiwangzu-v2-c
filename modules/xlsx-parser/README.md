# xlsx-parser — XLSX/CSV Parser

解析 XLS/XLSX/CSV 文件为统一内容块。

## 对外能力

| 能力 | 说明 |
|------|------|
| `parse` | Parse XLS/XLSX/CSV files into unified content blocks |

## 接口

后端前缀：`/api/xlsx-parser`

| 路径族 | 方法 |
|------|------|
| /health | GET |
| /parse | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/xlsx-parser/sandbox/test_module.py
cd modules/xlsx-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module xlsx-parser --check
```
