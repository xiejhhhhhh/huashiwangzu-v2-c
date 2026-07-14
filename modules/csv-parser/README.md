# csv-parser — CSV Parser

解析 CSV/TSV 文件为统一内容块。

## 对外能力

| 能力 | 说明 |
|------|------|
| `parse` | Parse CSV/TSV files into unified content blocks |

## 接口

后端前缀：`/api/csv-parser`

| 路径族 | 方法 |
|------|------|
| /health | GET |
| /parse | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/csv-parser/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module csv-parser --check
```
